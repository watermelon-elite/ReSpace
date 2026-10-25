// Record fields and matrix encoding from Wes Bos's ScanBundle.swift (31b2dc9, MIT).
import ARKit
import Foundation
import UIKit

struct ScanBundle {
  let url: URL
  func file(_ path: String) -> URL { url.appendingPathComponent(path) }
}
struct PhotoView {
  var position: SIMD3<Float>
  var forward: SIMD3<Float>
  init(transform: simd_float4x4) {
    position = simd_make_float3(transform.columns.3)
    forward = -simd_normalize(simd_make_float3(transform.columns.2))
  }
}
extension simd_float4x4 {
  var columnMajor: [Float] {
    [columns.0, columns.1, columns.2, columns.3].flatMap { [$0.x, $0.y, $0.z, $0.w] }
  }
}

extension simd_float3x3 {
  var columnMajor: [Float] {
    [columns.0, columns.1, columns.2].flatMap { [$0.x, $0.y, $0.z] }
  }
}

extension UIDevice {
  /// e.g. "iPhone16,1"
  static var modelIdentifier: String {
    var info = utsname()
    uname(&info)
    return withUnsafeBytes(of: &info.machine) { buf in
      String(decoding: buf.prefix { $0 != 0 }, as: UTF8.self)
    }
  }
}
