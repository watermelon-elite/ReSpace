import Foundation

/// Projects an ARKit camera-space point into the unrotated, top-left-origin sensor JPEG.
/// Validate calibration once per photo; the mesh path projects without per-vertex arrays.
struct ScanColorProjection {
    private let intrinsics: SIMD4<Float>
    private let width: Float
    private let height: Float

    init?(intrinsics k: [Float], width: Int, height: Int) {
        guard k.count == 4, k.allSatisfy(\.isFinite), k[0] > 0, k[1] > 0, width > 0, height > 0 else { return nil }
        intrinsics = SIMD4(k[0],k[1],k[2],k[3]); self.width = Float(width); self.height = Float(height)
    }
    func pixel(cameraPoint p: SIMD3<Float>) -> SIMD2<Float>? {
        guard p.x.isFinite, p.y.isFinite, p.z.isFinite, p.z < -0.1 else { return nil }
        let u = intrinsics.x * p.x / -p.z + intrinsics.z
        let v = intrinsics.w - intrinsics.y * p.y / -p.z
        guard u >= 0, u < width, v >= 0, v < height else { return nil }
        return SIMD2(u,v)
    }
    static func pixel(cameraPoint p: [Float], intrinsics: [Float], width: Int, height: Int) -> [Float]? {
        guard p.count == 3, let projection = Self(intrinsics: intrinsics, width: width, height: height),
              let pixel = projection.pixel(cameraPoint: SIMD3(p[0],p[1],p[2])) else { return nil }
        return [pixel.x,pixel.y]
    }
}
