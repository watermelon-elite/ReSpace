// Derived from Wes Bos's ScanView.swift at 31b2dc9 (MIT).
import ARKit
import CoreImage
import ImageIO
/// Records LiDAR depth frames (with pose + intrinsics) up to 5× a second while moving:
/// zlib-compressed Float16 depth + UInt8 confidence + a 640×480 color JPEG of the same
/// frame. A full RGB-D sequence, so the Mac can build a fully colored mesh.
final class DepthRecorder: @unchecked Sendable {
  typealias Record = SourceDepthRecord

  private let bundle: ScanBundle
  private let queue = DispatchQueue(label: "depth-writer", qos: .utility)
  private(set) var records: [Record] = []
  private var last: (time: TimeInterval, pose: simd_float4x4)?
  private var next = 0
  private var inFlight = 0
  private var recordingFailure: Error?
  var failure: Error? { recordingFailure }
  private let ci = CIContext()

  init(bundle: ScanBundle) {
    self.bundle = bundle
  }

  /// Call every frame; keeps one when the camera has moved or turned enough (≤ 5/s)
  func consider(_ frame: ARFrame, room: Int, camera: CameraState?, interval: TimeInterval = 0.2) {
    guard let depth = frame.sceneDepth, inFlight < 3 else { return }
    guard CVPixelBufferGetPixelFormatType(depth.depthMap) == kCVPixelFormatType_DepthFloat32 else {
      recordingFailure = ClientError.storage("The depth camera returned an unsupported pixel format.")
      return
    }
    if let confidence = depth.confidenceMap,
       (CVPixelBufferGetWidth(confidence) != CVPixelBufferGetWidth(depth.depthMap) || CVPixelBufferGetHeight(confidence) != CVPixelBufferGetHeight(depth.depthMap)) {
      recordingFailure = ClientError.storage("The depth and confidence dimensions disagree.")
      return
    }
    guard case .normal = frame.camera.trackingState else { return }
    let pose = frame.camera.transform
    if let last {
      let moved = simd_distance(pose.columns.3, last.pose.columns.3)
      let turned = acos(min(1, max(-1, simd_dot(simd_make_float3(pose.columns.2), simd_make_float3(last.pose.columns.2)))))
      guard frame.timestamp - last.time > interval, moved > 0.04 || turned > 0.06 else { return }
    }
    last = (frame.timestamp, pose)
    let w = CVPixelBufferGetWidth(depth.depthMap), h = CVPixelBufferGetHeight(depth.depthMap)
    let sx = Float(w) / Float(frame.camera.imageResolution.width)
    let sy = Float(h) / Float(frame.camera.imageResolution.height)
    var k = frame.camera.intrinsics
    k.columns.0.x *= sx; k.columns.1.y *= sy; k.columns.2.x *= sx; k.columns.2.y *= sy
    let name = String(format: "%05d", next)
    next += 1
    // color: downscale on the GPU now (so we don't hold ARKit's buffer), encode later
    let rgbScale = 640 / Float(frame.camera.imageResolution.width)
    var kc = frame.camera.intrinsics
    kc.columns.0.x *= rgbScale; kc.columns.1.y *= rgbScale; kc.columns.2.x *= rgbScale; kc.columns.2.y *= rgbScale
    let small = CIImage(cvPixelBuffer: frame.capturedImage).transformed(by: CGAffineTransform(scaleX: CGFloat(rgbScale), y: CGFloat(rgbScale)))
    let cg = ci.createCGImage(small, from: CGRect(x: 0, y: 0, width: 640, height: CGFloat((Float(frame.camera.imageResolution.height) * rgbScale).rounded())))
    if let cg {
      kc = frame.camera.intrinsics
      let sx = Float(cg.width)/Float(frame.camera.imageResolution.width), sy = Float(cg.height)/Float(frame.camera.imageResolution.height)
      kc.columns.0.x *= sx; kc.columns.1.y *= sy; kc.columns.2.x *= sx; kc.columns.2.y *= sy
    }
    let record = Record(
      file: "depth/\(name).f16z", confidence: "depth/\(name).conf", rgb: cg == nil ? nil : "depth/\(name).jpg",
      rgbIntrinsics: kc.columnMajor, camera: camera, room: room, timestamp: frame.timestamp,
      width: w, height: h, transform: pose.columnMajor, intrinsics: k.columnMajor)
    let depthData = Self.float16(depth.depthMap)
    let confData = depth.confidenceMap.map(Self.bytes)
    inFlight += 1
    queue.async {
      do {
        // A .f16z is always compressed; never silently put raw bytes under that extension.
        let compressed = try (depthData as NSData).compressed(using: .zlib) as Data
        try compressed.write(to: self.bundle.file(record.file), options: .atomic)
        try confData?.write(to: self.bundle.file(record.confidence), options: .atomic)
        if let cg, let rgb = record.rgb {
          guard let dest = CGImageDestinationCreateWithURL(self.bundle.file(rgb) as CFURL, "public.jpeg" as CFString, 1, nil) else {
            throw ClientError.storage("A depth color image could not be saved.")
          }
          CGImageDestinationAddImage(dest, cg, [kCGImageDestinationLossyCompressionQuality: 0.8] as CFDictionary)
          guard CGImageDestinationFinalize(dest) else { throw ClientError.storage("A depth color image could not be saved.") }
        }
        DispatchQueue.main.async { self.records.append(record); self.inFlight -= 1 }
      } catch {
        let failure = SourceCaptureStorage.failure(error, at: self.bundle.file(record.file))
        DispatchQueue.main.async { self.recordingFailure = failure; self.inFlight -= 1 }
      }
    }
  }

  /// All accepted writes and their main-queue receipts precede this completion.
  @MainActor func finish() async throws {
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
      queue.async { DispatchQueue.main.async { continuation.resume() } }
    }
    if let recordingFailure { throw recordingFailure }
    try save()
  }

  func save() throws {
    try SourceCaptureStorage.writeJSON(records, to: bundle.file("depth/frames.json"), prettyPrinted: true)
  }

  func discard(room: Int) {
    for r in records where r.room == room {
      try? FileManager.default.removeItem(at: bundle.file(r.file))
      try? FileManager.default.removeItem(at: bundle.file(r.confidence))
      if let rgb = r.rgb { try? FileManager.default.removeItem(at: bundle.file(rgb)) }
    }
    records.removeAll { $0.room == room }
  }

  static func float16(_ buffer: CVPixelBuffer) -> Data {
    CVPixelBufferLockBaseAddress(buffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
    let w = CVPixelBufferGetWidth(buffer), h = CVPixelBufferGetHeight(buffer)
    let row = CVPixelBufferGetBytesPerRow(buffer)
    let base = CVPixelBufferGetBaseAddress(buffer)!
    var out = [Float16](repeating: 0, count: w * h)
    for y in 0..<h {
      let src = base.advanced(by: y * row).assumingMemoryBound(to: Float32.self)
      for x in 0..<w { out[y * w + x] = Float16(src[x]) }
    }
    return out.withUnsafeBufferPointer { Data(buffer: $0) }
  }

  static func bytes(_ buffer: CVPixelBuffer) -> Data {
    CVPixelBufferLockBaseAddress(buffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
    let w = CVPixelBufferGetWidth(buffer), h = CVPixelBufferGetHeight(buffer)
    let row = CVPixelBufferGetBytesPerRow(buffer)
    let base = CVPixelBufferGetBaseAddress(buffer)!
    var out = Data(capacity: w * h)
    for y in 0..<h { out.append(base.advanced(by: y * row).assumingMemoryBound(to: UInt8.self), count: w) }
    return out
  }

  /// 64×48 grid of each block's median depth (robust to LiDAR speckle; low-confidence
  /// pixels ignored), for the coverage engine's occlusion test
  static func grid(for frame: ARFrame, cells: (Int, Int) = (64, 48)) -> CoverageEngine.DepthGrid? {
    guard let sd = frame.sceneDepth else { return nil }
    let depth = sd.depthMap
    CVPixelBufferLockBaseAddress(depth, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(depth, .readOnly) }
    let conf = sd.confidenceMap
    if let conf, CVPixelBufferGetWidth(conf) != CVPixelBufferGetWidth(depth) || CVPixelBufferGetHeight(conf) != CVPixelBufferGetHeight(depth) { return nil }
    if let conf { CVPixelBufferLockBaseAddress(conf, .readOnly) }
    defer { if let conf { CVPixelBufferUnlockBaseAddress(conf, .readOnly) } }
    let w = CVPixelBufferGetWidth(depth), h = CVPixelBufferGetHeight(depth)
    let row = CVPixelBufferGetBytesPerRow(depth)
    let base = CVPixelBufferGetBaseAddress(depth)!
    let confBase = conf.flatMap { CVPixelBufferGetBaseAddress($0) }
    let confRow = conf.map { CVPixelBufferGetBytesPerRow($0) } ?? 0
    let (gw, gh) = cells
    var buckets = [[Float]](repeating: [], count: gw * gh)
    for y in 0..<h {
      let src = base.advanced(by: y * row).assumingMemoryBound(to: Float32.self)
      let c = confBase?.advanced(by: y * confRow).assumingMemoryBound(to: UInt8.self)
      let gy = y * gh / h
      for x in 0..<w {
        let v = src[x]
        guard v.isFinite, v > 0, (c?[x] ?? 2) >= 1 else { continue }
        buckets[gy * gw + x * gw / w].append(v)
      }
    }
    let values = buckets.map { b -> Float in
      guard !b.isEmpty else { return 0 } // unknown: the engine skips the test there
      let s = b.sorted()
      return s[s.count / 2]
    }
    let sx = Float(gw) / Float(frame.camera.imageResolution.width), sy = Float(gh) / Float(frame.camera.imageResolution.height)
    let k = frame.camera.intrinsics
    return CoverageEngine.DepthGrid(
      width: gw, height: gh, values: values, worldToCamera: frame.camera.transform.inverse,
      fx: k.columns.0.x * sx, fy: k.columns.1.y * sy, cx: k.columns.2.x * sx, cy: k.columns.2.y * sy)
  }
}
