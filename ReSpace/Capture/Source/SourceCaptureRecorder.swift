// Capture mechanics ported from Wes Bos, 31b2dc9 (MIT); see Source/LICENSE.
// ReSpace integration is one new Room/session, without multi-house continuation.
import ARKit
import CoreImage
import CoreImage.CIFilterBuiltins
import ImageIO
import RoomPlan
import UIKit
import UniformTypeIdentifiers

@MainActor
final class SourceCaptureRecorder: NSObject {
  enum Phase { case scanning, finishingRoom, finished }
  let arSession: ARSession
  let bundle: ScanBundle
  let engine = CoverageEngine()
  private(set) lazy var scanView = SourceScanView(session: arSession, engine: engine)
  private lazy var depthRecorder = DepthRecorder(bundle: bundle)
  private let cameraControl = CameraControl()
  var onUpdate: (() -> Void)?
  var highResolutionPhotos = true
  private(set) var photos: [PhotoRecord] = []
  private(set) var stats = CoverageEngine.Stats()
  private(set) var lastWarning: String?
  private(set) var recordingError: Error?
  private var diagnostics = SourceCaptureDiagnostics()
  private var rawRoomArchive = SourceCaptureStorage.RawRoomArchive()
  private var recovery = TrackingRecovery()
  private var phase: Phase = .scanning
  private var closed = false
  private var paused = false
  private let roomIndex = 0
  private var liveRoom: CapturedRoom?
  private var photoViews: [(room: Int, view: PhotoView)] = []
  private var enginePhotos: [CoverageEngine.Photo] = []
  private var candidate: Shot?
  private var previousPose: (time: TimeInterval, pose: simd_float4x4)?
  private var poseHistory: [(time: TimeInterval, pose: simd_float4x4)] = []
  private var lastBlur: Float?
  private var lastPhotoTime: TimeInterval = 0
  private var photosInFlight = 0
  private var nextPhotoID = 0
  private var roomPhotoCount = 0
  private var highResSupported = true
  private var highResInFlight = false
  private var highResRequestID: UUID?
  private var lastHighResRequest: TimeInterval = -.infinity
  private var meshReady = false
  private var meshReadyAt: TimeInterval?
  private var lastMeshCheck: TimeInterval = 0
  private var lastEvaluate: TimeInterval = 0
  private var lastRoomToEngine: TimeInterval = 0
  private var lastPublish: TimeInterval = 0
  private var wasFeeding = false
  private var lastDiagnostic: TimeInterval = 0
  private var memoryPressureUntil: TimeInterval = 0
  private var displayLink: CADisplayLink?
  private let ciContext = CIContext(options: [.cacheIntermediates: false])
  private let startedAt = Date()
  private let autoPhotos = true
  var captureReady: Bool { meshReady && recovery.canCapture && !closed }
  var canTakePhoto: Bool { phase == .scanning && !paused && captureReady && !highResInFlight && photosInFlight == 0 }
  var canFinish: Bool { !photos.isEmpty && phase == .scanning }
  var elapsedSeconds: Int { Int(Date().timeIntervalSince(startedAt)) }
  var captureBudget: CaptureBudget { CaptureBudget(thermal: ProcessInfo.processInfo.thermalState, photos: roomPhotoCount, memoryPressure: CACurrentMediaTime() < memoryPressureUntil) }
  var guidance: String {
    if let issue = recovery.issue { return issue.message }
    if let lastWarning { return lastWarning }
    switch engine.latestHint {
    case .lookUp: return "Tilt up to photograph higher surfaces."
    case .lookDown: return "Tilt down to photograph lower surfaces."
    case .getCloser: return "Move closer to surfaces that need more photo detail."
    case .turn: return "Turn slowly toward the red surfaces."
    case .done: return "Good photo detail. Review any gaps before saving."
    case .none: return "Move slowly. Red surfaces need photos; green surfaces have good photo detail."
    }
  }

  init(session: ARSession, directory: URL) throws {
    arSession = session
    bundle = ScanBundle(url: directory)
    super.init()
    for folder in ["rooms","photos","depth","mesh"] {
      try FileManager.default.createDirectory(at: directory.appendingPathComponent(folder), withIntermediateDirectories: true)
    }
    engine.onStats = { [weak self] stats in self?.stats = stats; self?.onUpdate?() }
    scanView.onSessionFailure = { [weak self] errors in self?.recordingError = ClientError.storage(errors.joined(separator: " · ")) }
    scanView.onSessionEvent = { [weak self] event in
      guard let self else { return }
      self.diagnostics.log(event, since: self.startedAt)
      self.candidate = nil
      self.recovery.update(problem: .interrupted, now: CACurrentMediaTime())
    }
    NotificationCenter.default.addObserver(self, selector: #selector(memoryWarning), name: UIApplication.didReceiveMemoryWarningNotification, object: nil)
    try writeManifest(completed: false, room: nil, mesh: nil)
  }
  func start() {
    let link = CADisplayLink(target: self, selector: #selector(tick))
    link.preferredFrameRateRange = CAFrameRateRange(minimum: 30, maximum: 60, preferred: 60)
    link.add(to: .main, forMode: .common); displayLink = link
    UIApplication.shared.isIdleTimerDisabled = true
  }
  func updateRoom(_ room: CapturedRoom) {
    liveRoom = room; scanView.showRoom(room)
    if CACurrentMediaTime()-lastRoomToEngine > 0.4 {
      lastRoomToEngine = CACurrentMediaTime(); engine.setRoom(room)
    }
  }
  @objc private func memoryWarning() { memoryPressureUntil = CACurrentMediaTime()+60; candidate = nil }
  @objc private func tick() {
    guard phase == .scanning, !closed else { return }
    if let failure = depthRecorder.failure { recordingError = failure; onUpdate?(); return }
    let now = CACurrentMediaTime()
    let frame = arSession.currentFrame
    let problem: TrackingRecovery.Issue?
    if let frame, now-frame.timestamp < 0.5 { problem = TrackingRecovery.problem(for: frame.camera.trackingState) }
    else { problem = .stalled }
    recovery.update(problem: problem, now: now)
    if captureReady, !wasFeeding { scanView.refeedEngine(from: arSession) }
    scanView.feed.isOn = captureReady
    wasFeeding = captureReady
    if !captureReady { candidate = nil }
    if now-lastPublish > 1.0/15 { lastPublish = now; onUpdate?() }
    guard let frame, frame.timestamp != previousPose?.time else { return }
    if let previous = previousPose {
      lastBlur = Self.predictedBlur(frame: frame, previous: previous)
      let jump = simd_distance(frame.camera.transform.columns.3, previous.pose.columns.3)
      if jump > 0.5, frame.timestamp-previous.time < 0.2 {
        diagnostics.log("World jump \(jump) m; review alignment", since: startedAt)
      }
    }
    previousPose = (frame.timestamp,frame.camera.transform)
    poseHistory.append((frame.timestamp,frame.camera.transform))
    if poseHistory.count > 90 { poseHistory.removeFirst(poseHistory.count-90) }
    if frame.timestamp-lastMeshCheck > 0.5 { lastMeshCheck = frame.timestamp; ensureMeshAndDepth() }
    if !cameraControl.whiteBalanceLocked, let ready = meshReadyAt, now-ready > 3 {
      cameraControl.lockWhiteBalance(); diagnostics.whiteBalance = cameraControl.summary
    }
    guard !paused, captureReady else { return }
    if now-lastDiagnostic > 5 { lastDiagnostic = now; sampleDiagnostics(force: true) }
    depthRecorder.consider(frame, room: roomIndex, camera: cameraControl.state(for: frame), interval: captureBudget.depthInterval)
    if frame.timestamp-lastEvaluate > captureBudget.evaluationInterval {
      lastEvaluate = frame.timestamp
      engine.evaluate(view: Self.enginePhoto(frame: frame, sharpness: 1, depth: nil, room: roomIndex))
    }
    if let lastBlur { autoPhoto(frame, blur: lastBlur) }
  }

  /// A frame worth keeping, held until a sharper one of the same view comes along.
  /// The pixel buffer is copied so ARKit's frame pool isn't starved.
  fileprivate struct Shot: @unchecked Sendable { // pixel buffers are safe to hand across threads
    var buffer: CVPixelBuffer
    var transform: simd_float4x4
    var intrinsics: simd_float3x3
    var resolution: CGSize
    var timestamp: TimeInterval
    var tracking: String
    var exposure: TimeInterval
    /// predicted motion blur in pixels (0 for manual stills we don't measure)
    var blur: Float
    var depth: CoverageEngine.DepthGrid?
    var highRes = false
    var camera: CameraState?
  }

  func takePhoto() {
    guard canTakePhoto, let frame = arSession.currentFrame,
          CACurrentMediaTime() - frame.timestamp < 0.5,
          case .normal = frame.camera.trackingState,
          let buffer = Self.copy(frame.capturedImage) else { return }
    candidate = nil
    var shot = Shot(frame: frame, buffer: buffer, blur: lastBlur ?? 0)
    shot.depth = DepthRecorder.grid(for: frame)
    shot.camera = cameraControl.state(for: frame)
    save(shot, manual: true)
  }

  /// Wait for accepted JPEG writes. A still request has a timeout; late callbacks are
  /// invalidated so they cannot attach a photo to the next room.
  private func drainPhotos() async {
    let deadline = CACurrentMediaTime() + 3
    while highResInFlight && CACurrentMediaTime() < deadline && !closed {
      try? await Task.sleep(for: .milliseconds(50))
    }
    if highResInFlight {
      highResRequestID = nil
      highResInFlight = false
      diagnostics.log("high-resolution request timed out while finishing", since: startedAt)
    }
    while photosInFlight > 0 && !closed {
      try? await Task.sleep(for: .milliseconds(50))
    }
  }

  /// How far the image smears during this frame's exposure, in pixels: rotation
  /// speed × exposure × focal length, plus translation assuming things ~2 m away.
  /// Computed from ARKit's poses, so it costs nothing per frame.
  private static func predictedBlur(frame: ARFrame, previous: (time: TimeInterval, pose: simd_float4x4)) -> Float {
    let dt = Float(frame.timestamp - previous.time)
    guard dt > 0 else { return .infinity }
    let q0 = simd_quatf(previous.pose), q1 = simd_quatf(frame.camera.transform)
    let delta = q0.inverse * q1
    let angle = 2 * acos(min(1, abs(delta.real)))
    let moved = simd_distance(previous.pose.columns.3, frame.camera.transform.columns.3)
    let exposure = Float(frame.camera.exposureDuration > 0 ? frame.camera.exposureDuration : 1.0 / 60)
    let focal = frame.camera.intrinsics.columns.0.x
    return focal * exposure * (angle / dt + (moved / dt) / 2)
  }

  /// Blur for a frame that isn't the latest (a high-res still): camera motion from the pose history
  private func blur(at time: TimeInterval, for frame: ARFrame) -> Float? {
    guard let after = poseHistory.firstIndex(where: { $0.time >= time }), after > 0 else { return nil }
    let a = poseHistory[after - 1], b = poseHistory[after]
    let dt = Float(b.time - a.time)
    guard dt > 0 else { return nil }
    let angle = 2 * acos(min(1, abs((simd_quatf(a.pose).inverse * simd_quatf(b.pose)).real)))
    let moved = simd_distance(a.pose.columns.3, b.pose.columns.3)
    let exposure = Float(frame.camera.exposureDuration > 0 ? frame.camera.exposureDuration : 1.0 / 60)
    return frame.camera.intrinsics.columns.0.x * exposure * (angle / dt + (moved / dt) / 2)
  }

  /// Shoot where it pays off. Once there's mesh (or RoomPlan surfaces) to score against,
  /// the engine estimates how much red the current view would turn green; before that,
  /// any new viewpoint counts. Either way, hold the sharpest frame of that view.
  private func autoPhoto(_ frame: ARFrame, blur: Float) {
    guard autoPhotos, photosInFlight == 0, !highResInFlight, case .normal = frame.camera.trackingState else { return }
    let view = PhotoView(transform: frame.camera.transform)
    if resolveCandidate(frame: frame, view: view) { return }
    guard frame.timestamp - lastPhotoTime > captureBudget.photoInterval, blur <= Self.acceptableBlur else { return }
    let recent = photoViews.suffix(8)
    guard recent.allSatisfy({ simd_distance($0.view.position, view.position) > 0.12 || simd_dot($0.view.forward, view.forward) < cos(Float.pi / 18) }) else { return }
    if stats.meshArea > 0.5 || stats.targetsCovered > 0 || liveRoom != nil {
      guard engine.latestGain > Self.minimumGain else { return }
    } else {
      guard abs(view.forward.y) < 0.75 else { return }
      let isNew = photoViews.allSatisfy { simd_distance($0.view.position, view.position) > 0.5 || simd_dot($0.view.forward, view.forward) < cos(Float.pi / 7) }
      guard isNew else { return }
    }
    hold(frame, blur: blur)
  }

  /// Save the held frame once it's sharp enough, or once you've moved on from that view.
  /// Returns true if it handled this tick.
  private func resolveCandidate(frame: ARFrame, view: PhotoView) -> Bool {
    guard let held = candidate else { return false }
    let heldView = PhotoView(transform: held.transform)
    let movedOn = simd_distance(heldView.position, view.position) > 0.3 || simd_dot(heldView.forward, view.forward) < cos(Float.pi / 12)
    let stale = frame.timestamp - held.timestamp > 1.2
    guard held.blur <= Self.sharpBlur || movedOn || stale else { return false }
    commitCandidate()
    return true
  }

  private func hold(_ frame: ARFrame, blur: Float) {
    if let held = candidate, blur > held.blur * 0.8 { return } // only copy clearly better frames
    guard let copy = Self.copy(frame.capturedImage) else { return }
    var shot = Shot(frame: frame, buffer: copy, blur: blur)
    shot.depth = DepthRecorder.grid(for: frame)
    shot.camera = cameraControl.state(for: frame)
    candidate = shot
  }

  /// Save the held frame, trying for a full-resolution still of the same view first and
  /// keeping it if it came out at least as sharp (relative to its size).
  private func commitCandidate(allowHighResolution: Bool = true) {
    guard let held = candidate else { return }
    candidate = nil
    guard held.blur <= Self.acceptableBlur else { return }
    guard !captureBudget.constrained, allowHighResolution, highResolutionPhotos, highResSupported, !highResInFlight,
          captureReady, phase == .scanning,
          ProcessInfo.processInfo.thermalState == .nominal,
          CACurrentMediaTime() - lastHighResRequest >= 3 else {
      save(held, manual: false)
      return
    }
    highResInFlight = true
    lastHighResRequest = CACurrentMediaTime()
    let requestID = UUID()
    highResRequestID = requestID
    diagnostics.log("high-resolution photo requested", since: startedAt)
    arSession.captureHighResolutionFrame { [weak self] frame, error in
      Task { @MainActor [weak self] in
        guard let self, self.highResRequestID == requestID else { return }
        self.highResInFlight = false
        self.highResRequestID = nil
        guard !self.closed, !self.paused, self.captureReady,
              self.phase == .scanning || self.phase == .finishingRoom else { return }
        guard let frame, let blur = self.blur(at: frame.timestamp, for: frame) else {
          if let error {
            self.highResSupported = false // don't keep asking
            self.diagnostics.recordFailure(source: "high-resolution photo", chain: [error.localizedDescription], since: self.startedAt)
            self.sampleDiagnostics(force: true)
          }
          self.save(held, manual: false)
          return
        }
        guard case .normal = frame.camera.trackingState else {
          self.save(held, manual: false)
          return
        }
        let relative = blur / Float(frame.camera.imageResolution.width) * 1920
        let heldView = PhotoView(transform: held.transform), hrView = PhotoView(transform: frame.camera.transform)
        let sameView = simd_distance(heldView.position, hrView.position) < 0.2 && simd_dot(heldView.forward, hrView.forward) > cos(Float.pi / 15)
        if frame.camera.imageResolution.width > held.resolution.width, relative <= max(held.blur, Self.sharpBlur) * 1.2, sameView {
          guard let buffer = Self.copy(frame.capturedImage) else {
            self.save(held, manual: false)
            return
          }
          var shot = Shot(frame: frame, buffer: buffer, blur: blur)
          shot.depth = held.depth // depth from the video frame a moment earlier (same view)
          shot.highRes = true
          shot.camera = self.cameraControl.state(for: frame)
          self.save(shot, manual: false)
        } else {
          self.save(held, manual: false)
        }
      }
    }
  }

  /// Under ~1.5 px of smear (at 1920 wide) is effectively sharp; up to 6 px is still usable.
  nonisolated private static let sharpBlur: Float = 1.5
  nonisolated private static let acceptableBlur: Float = 6
  /// m² of not-yet-covered surface a photo must add
  private static let minimumGain: Float = 0.06
  /// long edge of saved photos; full-res stills are scaled down to this
  private static let maxPhotoEdge: CGFloat = 3024

  private func save(_ shot: Shot, manual: Bool) {
    // auto photos wait their turn; manual taps always go through (within reason)
    guard !closed, phase == .scanning || phase == .finishingRoom,
          photosInFlight < (manual ? 3 : 1), !paused || manual else { return }
    photosInFlight += 1
    lastPhotoTime = shot.timestamp

    let fileName = String(format: "%04d.jpg", nextPhotoID)
    nextPhotoID += 1
    let scale = min(1, Self.maxPhotoEdge / max(shot.resolution.width, shot.resolution.height))
    var k = shot.intrinsics
    k.columns.0.x *= Float(scale); k.columns.1.y *= Float(scale); k.columns.2.x *= Float(scale); k.columns.2.y *= Float(scale)
    let size = CGSize(width: (shot.resolution.width * scale).rounded(), height: (shot.resolution.height * scale).rounded())
    let record = PhotoRecord(
      file: "photos/\(fileName)",
      room: roomIndex,
      timestamp: shot.timestamp,
      width: Int(size.width),
      height: Int(size.height),
      transform: shot.transform.columnMajor,
      intrinsics: k.columnMajor,
      tracking: shot.tracking,
      manual: manual,
      exposure: shot.exposure,
      blurPixels: manual ? nil : shot.blur * Float(scale),
      pass: "scan",
      highRes: shot.highRes,
      camera: shot.camera
    )
    let view = PhotoView(transform: shot.transform)
    let enginePhoto = CoverageEngine.Photo(
      worldToCamera: shot.transform.inverse, position: view.position,
      fx: k.columns.0.x, fy: k.columns.1.y, cx: k.columns.2.x, cy: k.columns.2.y,
      width: Float(size.width), height: Float(size.height),
      sharpness: Self.sharpness(blurAt1920: shot.blur / Float(shot.resolution.width) * 1920),
      depth: shot.depth, room: record.room)
    var image = CIImage(cvPixelBuffer: shot.buffer)
    if scale < 1 {
      let f = CIFilter.lanczosScaleTransform()
      f.inputImage = image
      f.scale = Float(scale)
      f.aspectRatio = 1
      image = f.outputImage ?? image
    }
    let url = bundle.file(record.file)
    let context = ciContext
    Task.detached(priority: .utility) {
      let ok = Self.writeJPEG(image, to: url, context: context)
      await MainActor.run {
        defer { self.photosInFlight -= 1 }
        guard !self.closed else { return }
        if ok {
          self.photos.append(record)
          self.photoViews.append((record.room, view))
          self.enginePhotos.append(enginePhoto)
          self.engine.add(enginePhoto)
          self.roomPhotoCount += 1
          self.refreshCoverage()
        } else {
          self.lastWarning = "A photo could not be saved. Check available storage before continuing."
          self.recordingError = ClientError.storage("A photo could not be saved. The capture remains incomplete.")
          self.diagnostics.log("JPEG write failed: \(record.file)", since: self.startedAt)
        }
      }
    }
  }

  nonisolated static func sharpness(blurAt1920 b: Float) -> Float {
    b <= sharpBlur ? 1 : max(0.4, 1 - (b - sharpBlur) / (acceptableBlur - sharpBlur) * 0.6)
  }

  fileprivate static func enginePhoto(frame: ARFrame, sharpness: Float, depth: CoverageEngine.DepthGrid?, room: Int) -> CoverageEngine.Photo {
    let k = frame.camera.intrinsics, t = frame.camera.transform
    return CoverageEngine.Photo(
      worldToCamera: t.inverse, position: simd_make_float3(t.columns.3),
      fx: k.columns.0.x, fy: k.columns.1.y, cx: k.columns.2.x, cy: k.columns.2.y,
      width: Float(frame.camera.imageResolution.width), height: Float(frame.camera.imageResolution.height),
      sharpness: sharpness, depth: depth, room: room)
  }

  nonisolated private static func copy(_ src: CVPixelBuffer) -> CVPixelBuffer? {
    var out: CVPixelBuffer?
    let attrs = [kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary] as CFDictionary
    CVPixelBufferCreate(nil, CVPixelBufferGetWidth(src), CVPixelBufferGetHeight(src), CVPixelBufferGetPixelFormatType(src), attrs, &out)
    guard let dst = out else { return nil }
    CVPixelBufferLockBaseAddress(src, .readOnly)
    CVPixelBufferLockBaseAddress(dst, [])
    defer {
      CVPixelBufferUnlockBaseAddress(dst, [])
      CVPixelBufferUnlockBaseAddress(src, .readOnly)
    }
    for plane in 0..<CVPixelBufferGetPlaneCount(src) {
      guard let s = CVPixelBufferGetBaseAddressOfPlane(src, plane), let d = CVPixelBufferGetBaseAddressOfPlane(dst, plane) else { return nil }
      let rows = CVPixelBufferGetHeightOfPlane(src, plane)
      let sBytes = CVPixelBufferGetBytesPerRowOfPlane(src, plane), dBytes = CVPixelBufferGetBytesPerRowOfPlane(dst, plane)
      if sBytes == dBytes {
        memcpy(d, s, rows * sBytes)
      } else {
        for r in 0..<rows { memcpy(d + r * dBytes, s + r * sBytes, min(sBytes, dBytes)) }
      }
    }
    return dst
  }

  /// JPEG of the raw sensor image. Pixels stay in sensor orientation (so the saved
  /// intrinsics apply); EXIF orientation 6 makes Photos/Finder show it upright.
  nonisolated private static func writeJPEG(_ image: CIImage, to url: URL, context: CIContext) -> Bool {
    guard let cg = context.createCGImage(image, from: image.extent, format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)),
          let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.jpeg.identifier as CFString, 1, nil)
    else { return false }
    let props: [CFString: Any] = [
      kCGImagePropertyOrientation: 6,
      kCGImageDestinationLossyCompressionQuality: 0.85,
    ]
    CGImageDestinationAddImage(dest, cg, props as CFDictionary)
    return CGImageDestinationFinalize(dest)
  }

  private func ensureMeshAndDepth() {
    guard let c = arSession.configuration as? ARWorldTrackingConfiguration else { return }
    let depthOK = !ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) || c.frameSemantics.contains(.sceneDepth)
    let meshOK = c.sceneReconstruction.contains(.meshWithClassification)
    if meshOK, depthOK {
      if !meshReady {
        meshReady = true
        meshReadyAt = CACurrentMediaTime()
        diagnostics.detailConfiguration = "\(type(of: c)) reconstruction=\(c.sceneReconstruction.rawValue) semantics=\(c.frameSemantics.rawValue) video=\(Int(c.videoFormat.imageResolution.width))x\(Int(c.videoFormat.imageResolution.height)) worldMap=\(c.initialWorldMap != nil)"
      }
      return
    }
    guard let updated = c.copy() as? ARWorldTrackingConfiguration else { return }
    if diagnostics.roomPlanConfiguration == nil {
      diagnostics.roomPlanConfiguration = "\(type(of: c)) reconstruction=\(c.sceneReconstruction.rawValue) semantics=\(c.frameSemantics.rawValue) worldMap=\(c.initialWorldMap != nil)"
    }
    updated.initialWorldMap = nil
    updated.sceneReconstruction.insert(.meshWithClassification)
    if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) { updated.frameSemantics.insert(.sceneDepth) }
    meshReady = false
    diagnostics.configurationChanges += 1
    diagnostics.log("enable mesh/depth #\(diagnostics.configurationChanges): reconstruction \(c.sceneReconstruction.rawValue)→\(updated.sceneReconstruction.rawValue), semantics \(c.frameSemantics.rawValue)→\(updated.frameSemantics.rawValue)", since: startedAt)
    arSession.run(updated, options: []) // no reset: same world, RoomPlan keeps going
  }


  private func refreshCoverage() {
    do { try SourceCaptureStorage.writeJSON(photos, to: bundle.file("photos/photos.json")) }
    catch { recordingError = error }
    onUpdate?()
  }
  private func sampleDiagnostics(force: Bool = false) {
    do {
      let capacity = try bundle.url.resourceValues(forKeys: [.volumeAvailableCapacityKey]).volumeAvailableCapacity
      if let capacity, capacity < 512*1024*1024 { throw ClientError.storage("Free more storage before continuing this scan.") }
      try SourceCaptureStorage.writeJSON(diagnostics, to: bundle.file("diagnostics.json"))
    } catch { recordingError = error }
  }
  func freeze() async throws -> (vertices: Int, faces: Int, covered: Float) {
    commitCandidate(allowHighResolution: false)
    phase = .finishingRoom; scanView.feed.isOn = false
    displayLink?.invalidate(); displayLink = nil
    await drainPhotos()
    try await depthRecorder.finish()
    guard !closed else { throw CancellationError() }
    if let recordingError { throw recordingError }
    let result: Result<(vertices: Int, faces: Int, covered: Float), Error> = await withCheckedContinuation { c in
      engine.exportPLY(to: bundle.file("mesh/room-0.ply")) { c.resume(returning: $0) }
    }
    cameraControl.unlock()
    let mesh = try result.get()
    if mesh.faces == 0 {
      try? FileManager.default.removeItem(at: bundle.file("mesh/room-0.ply"))
      diagnostics.log("No mesh triangles; retaining available depth, photos and raw RoomPlan data", since: startedAt)
    }
    return mesh
  }
  func saveRawRoom(_ raw: CapturedRoomData) throws {
    rawRoomArchive = try SourceCaptureStorage.archiveRawRoom(raw, to: bundle.file("rooms/room-0-data.json"))
    if let warning = rawRoomArchive.warning { diagnostics.log(warning, since: startedAt) }
  }
  func complete(room: CapturedRoom?, mesh: (vertices: Int, faces: Int, covered: Float), layoutError: String?) async throws {
    guard !closed else { throw CancellationError() }
    try SourceCaptureStorage.writeJSON(photos, to: bundle.file("photos/photos.json"))
    if let room {
      try SourceCaptureStorage.writeJSON(room, to: bundle.file("rooms/room-0.json"))
      // These are optional RoomPlan previews, separate from the measured LiDAR mesh.
      do { try room.export(to: bundle.file("rooms/room-0.usdz"), exportOptions: .parametric) }
      catch {
        try? FileManager.default.removeItem(at: bundle.file("rooms/room-0.usdz"))
        diagnostics.log("Optional RoomPlan preview: " + error.localizedDescription, since: startedAt)
      }
      do { try room.export(to: bundle.file("rooms/room-0-mesh.usdz"), exportOptions: .mesh) }
      catch {
        try? FileManager.default.removeItem(at: bundle.file("rooms/room-0-mesh.usdz"))
        diagnostics.log("Optional RoomPlan detail mesh: " + error.localizedDescription, since: startedAt)
      }
    }
    if let layoutError { diagnostics.log("RoomPlan layout unavailable: " + layoutError, since: startedAt) }
    sampleDiagnostics(force: true)
    if let recordingError { throw recordingError }
    try writeManifest(completed: true, room: room, mesh: mesh, layoutError: layoutError)
    let directory = bundle.url
    let seal = try await Task.detached(priority: .utility) { try SourceBundleIntegrity.create(at: directory) }.value
    guard !closed else { throw CancellationError() }
    try SourceCaptureStorage.writeJSON(seal, to: bundle.file("integrity.json"))
    phase = .finished; stop()
  }
  func stop() {
    closed = true; candidate = nil; highResRequestID = nil
    displayLink?.invalidate(); displayLink = nil
    scanView.feed.isOn = false; cameraControl.unlock()
    UIApplication.shared.isIdleTimerDisabled = false
    NotificationCenter.default.removeObserver(self)
  }
  func drainAfterStop() async {
    while photosInFlight > 0 { try? await Task.sleep(for: .milliseconds(25)) }
    try? await depthRecorder.finish()
  }
  private func writeManifest(completed: Bool, room: CapturedRoom?, mesh: (vertices: Int, faces: Int, covered: Float)?, layoutError: String? = nil) throws {
    let capture = bundle.url.deletingLastPathComponent().lastPathComponent
    var result: [String: Any] = [
      "format":"house-capture/5", "state":completed ? "completed" : "recording",
      "createdAt":ISO8601DateFormatter().string(from: startedAt),
      "device":UIDevice.modelIdentifier, "systemVersion":UIDevice.current.systemVersion,
      "house":capture, "session":capture, "zone":capture,
      "coordinateSystem":"ARKit session world: meters, +Y up, right-handed; one fresh session",
      "photos":"photos/photos.json", "photoCount":photos.count,
      "depthFrames":"depth/frames.json", "depthFrameCount":depthRecorder.records.count,
      "sourceRevision":"31b2dc9da3fb541e501f2f0936e55b32afb70ee8"
    ]
    result["integrityFile"] = "integrity.json"
    if let layoutError { result["layoutError"] = layoutError }
    if let mesh {
      var record: [String: Any] = [
        "index":0, "name":"Room", "file":room == nil ? "" : "rooms/room-0.json",
        "usdz":FileManager.default.fileExists(atPath: bundle.file("rooms/room-0.usdz").path) ? "rooms/room-0.usdz" : "",
        "capturedAt":ISO8601DateFormatter().string(from: Date()),
        "walls":room?.walls.count ?? 0, "doors":room?.doors.count ?? 0, "windows":room?.windows.count ?? 0,
        "openings":room?.openings.count ?? 0, "objects":room?.objects.count ?? 0,
        "coverage":mesh.covered
      ]
      if let filename = rawRoomArchive.filename { record["data"] = "rooms/" + filename }
      if let warning = rawRoomArchive.warning { record["rawRoomDataError"] = warning }
      if mesh.faces > 0 {
        // Upstream uses zero for the merged PLY's unreported anchor count.
        record["mesh"] = ["file":"mesh/room-0.ply", "anchors":0,
                          "vertices":mesh.vertices, "faces":mesh.faces]
      }
      result["rooms"] = [record]
    } else { result["rooms"] = [] }
    let url = bundle.file("manifest.json")
    try SourceCaptureStorage.saving(url) {
      try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted,.sortedKeys]).write(to: url, options: .atomic)
    }
  }
  nonisolated fileprivate static func describeTracking(_ state: ARCamera.TrackingState) -> String {
    switch state { case .normal: "normal"; case .notAvailable: "notAvailable"; case .limited(let reason): "limited:\(reason)" }
  }
}

private struct SourceCaptureDiagnostics: Codable {
  struct Event: Codable { var t: Double; var what: String }
  var events: [Event] = []
  var whiteBalance: String?
  var roomPlanConfiguration: String?
  var detailConfiguration: String?
  var configurationChanges: Int = 0
  mutating func log(_ text: String, since start: Date) {
    events.append(Event(t: Date().timeIntervalSince(start),what: text))
    if events.count > 400 { events.removeFirst(events.count-400) }
  }
  mutating func recordFailure(source: String, chain: [String], since start: Date) { log(source+": "+chain.joined(separator: " · "), since: start) }
}

private extension SourceCaptureRecorder.Shot {
  init(frame: ARFrame, buffer: CVPixelBuffer, blur: Float) {
    self.init(
      buffer: buffer,
      transform: frame.camera.transform,
      intrinsics: frame.camera.intrinsics,
      resolution: frame.camera.imageResolution,
      timestamp: frame.timestamp,
      tracking: SourceCaptureRecorder.describeTracking(frame.camera.trackingState),
      exposure: frame.camera.exposureDuration,
      blur: blur
    )
  }
}


struct TrackingRecovery {
  enum Issue: Equatable {
    case starting, motion, features, relocalizing, unavailable, interrupted, stalled, settling

    var message: String {
      switch self {
      case .starting: return "Finding your position. Aim at a well-lit doorway or furniture and move slowly."
      case .motion: return "Slow down and hold steady. Keep a familiar doorway or furniture in view."
      case .features: return "Aim at well-lit furniture, shelves or a doorway. Blank walls are hard to track."
      case .relocalizing: return "Return to an area you just scanned and pan slowly so the phone can recognize it."
      case .unavailable: return "Position tracking is unavailable. Hold steady with the room in view."
      case .interrupted: return "Camera interrupted. Return to the app, then aim at an area you already scanned."
      case .stalled: return "Camera updates have stalled. Hold steady. If this persists, finish the room to save what you have."
      case .settling: return "Position found. Hold steady for a moment while tracking settles."
      }
    }
  }

  private(set) var issue: Issue? = .starting
  private var normalSince: TimeInterval?
  var canCapture: Bool { issue == nil }

  mutating func update(problem: Issue?, now: TimeInterval) {
    if let problem {
      issue = problem
      normalSince = nil
    } else if issue != nil {
      if normalSince == nil { normalSince = now }
      issue = now - (normalSince ?? now) >= 1.5 ? nil : .settling
    }
  }

  static func problem(for state: ARCamera.TrackingState) -> Issue? {
    switch state {
    case .normal: return nil
    case .notAvailable: return .unavailable
    case .limited(.initializing): return .starting
    case .limited(.excessiveMotion): return .motion
    case .limited(.insufficientFeatures): return .features
    case .limited(.relocalizing): return .relocalizing
    case .limited: return .unavailable
    }
  }
}
