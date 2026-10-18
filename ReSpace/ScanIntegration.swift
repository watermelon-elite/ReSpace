import Foundation

extension AppModel {
    func refreshScans() async {
        guard let scanStore else { return }
        do {
            localRooms = try await scanStore.captures.localRooms()
            scanRecoveries = try await scanStore.captures.manifests().filter { ["completed", "creating", "acquiring", "abandoned"].contains($0.state) }
        } catch { self.error = "Saved scans could not be opened: \(error.localizedDescription)" }
    }

    /// Resolve creation independently so rename/deletion can reconcile a lost reply without uploading the scan.
    func linkScan(_ id: String) async throws -> LocalSavedRoom {
        guard let scanStore, client != nil else { throw ContractError.invalid("Connect ReSpace before continuing. Your scan is saved on this iPhone.") }
        let repository = scanStore.captures
        let manifest = try await repository.load(id)
        var room = try await repository.localRoom(id)
        if room.backendRoomId == nil {
            let creationName = try await repository.backendCreationName(id)
            let result = try await submit(PendingRequest(path: "rooms", roomID: nil,
                body: ["operation_id": .string(manifest.creationId), "name": .string(creationName)]))
            guard let roomID = result["room"]["room_id"].string, let captureID = result["capture_id"].string else {
                throw ContractError.invalid("The backend did not acknowledge this scan's Room.")
            }
            try await repository.linkBackend(id, roomId: roomID, captureId: captureID)
            room = try await repository.localRoom(id)
            await refreshScans()
        }
        return room
    }

    /// Reconstruction retains all evidence; planning receives an evenly sampled, calibrated subset.
    func connectScan(_ id: String) async throws -> String {
        guard let scanStore, let client else { throw ContractError.invalid("Connect ReSpace before planning changes. Your scan is saved on this iPhone.") }
        let repository = scanStore.captures
        let manifest = try await repository.load(id)
        guard let export = manifest.roomExport else { throw ContractError.invalid("The saved scan has no completed room export.") }
        let room = try await linkScan(id)
        guard let roomID = room.backendRoomId, let captureID = room.backendCaptureId else { throw ContractError.invalid("The saved scan's backend link is incomplete.") }
        let detail = try await client.request("rooms/\(roomID)")
        if detail["capture_status"]["state"].text == "complete" { return roomID }
        var archive: CaptureArchive
        if let saved = CaptureArchive.recoverable().first(where: { $0.captureID == captureID }) {
            archive = saved
        } else {
            archive = CaptureArchive(roomID: roomID, captureID: captureID, startedAt: manifest.createdAt)
            archive.phase = "upload_pending"
        }
        // A complete retained transfer is reused byte-for-byte on retry.
        if archive.finalizeRequest == nil {
            try archive.save()
            archive.frames = []
            for (index, sourceIndex) in CaptureTransfer.indices(count: manifest.frames.count).enumerated() {
                try Task.checkCancellation()
                let frame = manifest.frames[sourceIndex]
                guard frame.metadata.captureId == id, frame.metadata.id == frame.id else {
                    throw ContractError.invalid("A retained frame belongs to a different scan.")
                }
                var parts: [String: Data] = [:]
                for artifact in frame.artifacts where ["jpeg", "depth", "confidence"].contains(artifact.type) {
                    parts[artifact.type] = try await repository.bytes(artifact, captureId: id)
                }
                let metadata = try JSONDecoder().decode(JSONValue.self, from: Wire.encoder().encode(frame.metadata))
                let sourceParts = parts
                let (meta, converted) = try await Task.detached(priority: .utility) {
                    try CaptureTransfer.frame(metadata: metadata, parts: sourceParts, captureID: captureID, index: index)
                }.value
                for (kind, bytes) in converted {
                    try bytes.write(to: archive.folder.appendingPathComponent("\(frame.id).\(kind)"), options: [.atomic, .completeFileProtectionUnlessOpen])
                }
                archive.frames.append(meta)
            }
            let raw = try await repository.bytes(export, captureId: id)
            let descriptor = CaptureTransfer.descriptor(id: "export_\(captureID)", captureID: captureID, kind: "roomplan", format: "application/json", data: raw)
            let inventory: JSONValue = .object(["room_id": .string(roomID), "capture_id": .string(captureID),
                "final_export_artifact_id": descriptor["artifact_id"], "frames": .array(archive.frames.map { .object(["frame_id": $0["frame_id"], "idx": $0["idx"]]) }),
                "artifacts": .array(archive.frames.flatMap { $0["artifacts"].array } + [descriptor]), "completion_id": .string(manifest.finalizeId),
                "started_at": .string(manifest.createdAt), "completed_at": .string(ISO8601DateFormatter().string(from: Date()))])
            archive.finalizeRequest = PendingRequest(path: "rooms/\(roomID)/finalize", roomID: roomID,
                body: ["operation_id": .string(manifest.finalizeId), "capture_id": .string(captureID),
                       "raw_export_base64": .string(raw.base64EncodedString()), "export_descriptor": descriptor, "manifest": inventory])
            try archive.save()
        }
        let transfer = CaptureController(archive: archive, app: self, client: client)
        await transfer.recover()
        guard transfer.finished else { throw ContractError.invalid(transfer.failure ?? "Your completed scan is retained. Try saving again.") }
        await refresh()
        return roomID
    }
}
