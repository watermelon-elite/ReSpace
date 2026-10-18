import Foundation

private func vector(_ values: [Float], count: Int, positive: Bool = false) -> Bool {
    values.count == count && values.allSatisfy { $0.isFinite && (!positive || $0 > 0) }
}
extension RoomSnapshot {
    func validateGeometry() throws {
        guard height.isFinite, (height > 0 || !validity.usable), (!validity.usable || floor.polygon.count >= 3),
              floor.polygon.allSatisfy({ vector($0, count: 2) }),
              vector(scanToRoomTransform, count: 16),
              Set(objects.map(\.id)).count == objects.count,
              walls.allSatisfy({ vector($0.a, count: 2) && vector($0.b, count: 2) && $0.a != $0.b && $0.height.isFinite && $0.height > 0 }),
              objects.allSatisfy({ vector($0.center, count: 2) && vector($0.size, count: 3, positive: true) && $0.baseElevation.isFinite && $0.yaw.isFinite }),
              openings.allSatisfy({ opening in
                  walls.contains { $0.id == opening.wallId } && opening.width.isFinite && opening.height.isFinite && opening.bottom.isFinite && opening.offset.isFinite && opening.width > 0 && opening.height > 0 && opening.bottom >= 0 && opening.offset >= 0
              }) else { throw ClientError.invalidGeometry }
    }
}
extension DesignVersion {
    func validateGeometry() throws {
        guard Set(items.map(\.id)).count == items.count,
              items.allSatisfy({ item in
                  vector(item.position, count: 3) && vector(item.size, count: 3, positive: true) && item.yaw.isFinite &&
                  (!item.isGhost || item.lastValid.map { vector($0.position, count: 3) && vector($0.size, count: 3, positive: true) && $0.yaw.isFinite } == true)
              }) else { throw ClientError.invalidGeometry }
    }
}
