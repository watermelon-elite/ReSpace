// Native capture records derived from Wes Bos, 31b2dc9 (MIT); see Capture/Source/LICENSE.
import Foundation

struct PhotoRecord: Codable {
  var file: String
  /// index of the room being scanned when this was taken
  var room: Int
  var timestamp: TimeInterval
  var width: Int
  var height: Int
  /// camera-to-world, column-major 4x4. ARKit camera looks down -Z, +Y up, +X right (in sensor orientation)
  var transform: [Float]
  /// column-major 3x3: fx, 0, 0, 0, fy, 0, cx, cy, 1
  var intrinsics: [Float]
  var tracking: String
  var manual: Bool
  /// shutter time in seconds
  var exposure: Double?
  /// predicted motion blur in pixels from camera motion during the exposure (auto photos)
  var blurPixels: Float?
  /// "layout" (RoomPlan pass) or "detail" (coverage pass)
  var pass: String?
  /// a full-resolution still rather than a video frame
  var highRes: Bool?
  /// camera state when the photo was taken, for normalizing brightness/color across photos
  var camera: CameraState?

  private enum CodingKeys: String, CodingKey {
    case file, room, timestamp, width, height, transform, intrinsics, tracking, manual
    case exposure, blurPixels, pass, highRes, camera
  }

  func encode(to encoder: Encoder) throws {
    var values = encoder.container(keyedBy: CodingKeys.self)
    try values.encode(file, forKey: .file)
    try values.encode(room, forKey: .room)
    try values.encode(timestamp, forKey: .timestamp)
    try values.encode(width, forKey: .width)
    try values.encode(height, forKey: .height)
    try values.encode(transform, forKey: .transform)
    try values.encode(intrinsics, forKey: .intrinsics)
    try values.encode(tracking, forKey: .tracking)
    try values.encode(manual, forKey: .manual)
    try values.encodeFiniteIfPresent(exposure, forKey: .exposure)
    try values.encodeFiniteIfPresent(blurPixels, forKey: .blurPixels)
    try values.encodeIfPresent(pass, forKey: .pass)
    try values.encodeIfPresent(highRes, forKey: .highRes)
    try values.encodeIfPresent(camera, forKey: .camera)
  }
}

/// Exposure + white balance + ARKit's light estimate for one frame
struct CameraState: Codable {
  /// sensor ISO
  var iso: Float?
  /// shutter time in seconds
  var shutter: Double?
  /// ARKit exposure offset (EV)
  var exposureOffset: Float?
  /// white-balance gains (red, green, blue), constant once white balance is locked
  var whiteBalance: [Float]?
  var whiteBalanceLocked: Bool?
  /// ARKit ambient light estimate: intensity (lumen, ~1000 = neutral) and color temperature (K)
  var ambientIntensity: Float?
  var colorTemperature: Float?

  private enum CodingKeys: String, CodingKey {
    case iso, shutter, exposureOffset, whiteBalance, whiteBalanceLocked, ambientIntensity, colorTemperature
  }

  func encode(to encoder: Encoder) throws {
    var values = encoder.container(keyedBy: CodingKeys.self)
    try values.encodeFiniteIfPresent(iso, forKey: .iso)
    try values.encodeFiniteIfPresent(shutter, forKey: .shutter)
    try values.encodeFiniteIfPresent(exposureOffset, forKey: .exposureOffset)
    // A missing channel makes the entire gain measurement unavailable; never shift channels.
    if let whiteBalance, whiteBalance.allSatisfy(\.isFinite) {
      try values.encode(whiteBalance, forKey: .whiteBalance)
    }
    try values.encodeIfPresent(whiteBalanceLocked, forKey: .whiteBalanceLocked)
    try values.encodeFiniteIfPresent(ambientIntensity, forKey: .ambientIntensity)
    try values.encodeFiniteIfPresent(colorTemperature, forKey: .colorTemperature)
  }
}

private extension KeyedEncodingContainer {
  /// Optional sensor estimates may be unavailable. JSON has no NaN or infinity.
  mutating func encodeFiniteIfPresent<T: BinaryFloatingPoint & Encodable>(_ value: T?, forKey key: Key) throws {
    if let value, value.isFinite { try encode(value, forKey: key) }
  }
}

struct SourceDepthRecord: Codable {
  /// Float16 meters, row-major, raw DEFLATE (zlib.decompress(data, -15) in Python)
  var file: String
  var confidence: String
  /// 640×480 JPEG of the camera image at this frame (sensor orientation, no EXIF rotation)
  var rgb: String?
  /// intrinsics for the rgb image (column-major 3×3)
  var rgbIntrinsics: [Float]?
  var camera: CameraState?
  var room: Int
  var timestamp: TimeInterval
  var width: Int
  var height: Int
  /// camera-to-world, column-major (same convention as photos)
  var transform: [Float]
  /// column-major 3x3, scaled to the depth map's resolution
  var intrinsics: [Float]
}
