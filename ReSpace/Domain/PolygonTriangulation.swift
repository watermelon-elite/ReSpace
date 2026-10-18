import Foundation

/// Ear clipping for drawing a simple, possibly concave floor. No placement logic.
enum PolygonTriangulation {
    static func indices(_ points: [[Float]]) -> [UInt32] {
        guard points.count >= 3, points.allSatisfy({ $0.count == 2 }) else { return [] }
        func cross(_ a: [Float], _ b: [Float], _ c: [Float]) -> Float {
            (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        }
        let area = points.indices.reduce(Float(0)) { sum, i in
            let next = points[(i + 1) % points.count]
            return sum + points[i][0] * next[1] - next[0] * points[i][1]
        }
        let indices = points.first == points.last ? Array(points.indices.dropLast()) : Array(points.indices)
        guard indices.count >= 3 else { return [] }
        var remaining = area > 0 ? indices : Array(indices.reversed())
        var triangles: [UInt32] = []
        while remaining.count > 3 {
            var clipped = false
            for i in remaining.indices {
                let a = remaining[(i + remaining.count - 1) % remaining.count]
                let b = remaining[i], c = remaining[(i + 1) % remaining.count]
                guard cross(points[a], points[b], points[c]) > 0.000001 else { continue }
                let contains = remaining.contains { p in
                    p != a && p != b && p != c && cross(points[a], points[b], points[p]) >= 0 &&
                    cross(points[b], points[c], points[p]) >= 0 && cross(points[c], points[a], points[p]) >= 0
                }
                guard !contains else { continue }
                // Reverse for upward (+Y) normals in the XZ plane.
                triangles += [UInt32(a), UInt32(c), UInt32(b)]
                remaining.remove(at: i); clipped = true; break
            }
            if !clipped { return [] }
        }
        triangles += [UInt32(remaining[0]), UInt32(remaining[2]), UInt32(remaining[1])]
        return triangles
    }
}
