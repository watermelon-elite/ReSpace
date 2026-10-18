import Foundation

struct WalkthroughEntity: Codable, Sendable {
    var id: String
    var label: String
    var category: String
    var kind: String
    var asset: String
    var localToScanTransform: [Double]
    var boundsMin: [Double]
    var boundsMax: [Double]
    var materialIds: [String]
    var supportId: String?
    var visible: Bool
    var moveReady: Bool
    var finishReady: Bool
    var collidable: Bool
    var observedFraction: Double
    var surfacePolygons: [[[Double]]]?
    var surfaceHoles: [[[Double]]]?
    var movable: Bool { ["furniture", "wall_decor"].contains(kind) }

    func worldPoint(_ point: [Double]) -> [Double] {
        let m = localToScanTransform
        return (0..<3).map { r in m[r]*point[0]+m[4+r]*point[1]+m[8+r]*point[2]+m[12+r] }
    }
    func footprint() -> [[Double]] {
        // Project all eight OBB corners; the convex hull avoids treating a rotated
        // object's world AABB as its collision geometry.
        var unsorted: [[Double]]=[]
        for x in [boundsMin[0],boundsMax[0]] { for y in [boundsMin[1],boundsMax[1]] { for z in [boundsMin[2],boundsMax[2]] {
            let p=worldPoint([x,y,z]);unsorted.append([p[0],p[2]])
        } } }
        let points=unsorted.sorted { $0[0] == $1[0] ? $0[1] < $1[1] : $0[0] < $1[0] }
        func cross(_ a: [Double], _ b: [Double], _ c: [Double]) -> Double {
            (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        }
        var lower: [[Double]] = [], upper: [[Double]] = []
        for p in points {
            while lower.count >= 2 && cross(lower[lower.count-2],lower.last!,p) <= 0 { lower.removeLast() }
            lower.append(p)
        }
        for p in points.reversed() {
            while upper.count >= 2 && cross(upper[upper.count-2],upper.last!,p) <= 0 { upper.removeLast() }
            upper.append(p)
        }
        return Array(lower.dropLast())+Array(upper.dropLast())
    }
}

struct WalkthroughMaterial: Codable, Sendable {
    var id: String
    var ownerId: String
    var slot: String
    var sourceMaterial: String
    var baseColor: [Double]
    var finish: String
    var repeatMeters: Double
}

struct WalkthroughNavigation: Codable, Sendable {
    var floorPolygons: [[[Double]]]
    var floorHeight: Double
    var spawnPosition: [Double]
    var spawnYaw: Double
    var eyeHeight: Double
    var playerRadius: Double
    var obstacles: [[[Double]]]

    static func contains(_ p: [Double], polygon: [[Double]]) -> Bool {
        var inside = false
        for i in polygon.indices {
            let a = polygon[i], b = polygon[(i+1)%polygon.count]
            if (a[1]>p[1]) != (b[1]>p[1]) && p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0] { inside.toggle() }
        }
        return inside
    }
    static func boundaryDistance(_ p: [Double], polygon: [[Double]]) -> Double {
        polygon.indices.map { i in
            let a = polygon[i], b = polygon[(i+1)%polygon.count]
            let dx=b[0]-a[0], dz=b[1]-a[1], length=dx*dx+dz*dz
            let t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dz)/max(length,1e-12)))
            return hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dz)
        }.min() ?? 0
    }
    static func polygonsOverlap(_ a: [[Double]], _ b: [[Double]]) -> Bool {
        if a.contains(where:{ contains($0,polygon:b) }) || b.contains(where:{ contains($0,polygon:a) }) { return true }
        func cross(_ a:[Double],_ b:[Double],_ c:[Double])->Double { (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]) }
        for i in a.indices { for j in b.indices {
            let p=a[i],q=a[(i+1)%a.count],r=b[j],s=b[(j+1)%b.count]
            if max(p[0],q[0])+1e-8<min(r[0],s[0]) || max(r[0],s[0])+1e-8<min(p[0],q[0]) || max(p[1],q[1])+1e-8<min(r[1],s[1]) || max(r[1],s[1])+1e-8<min(p[1],q[1]) { continue }
            if cross(p,q,r)*cross(p,q,s)<=1e-12 && cross(r,s,p)*cross(r,s,q)<=1e-12 { return true }
        } }
        return false
    }
    static func polygonContained(_ inner:[[Double]],in outer:[[Double]])->Bool {
        guard inner.allSatisfy({ contains($0,polygon:outer) }) else { return false }
        if outer.contains(where:{ contains($0,polygon:inner) && boundaryDistance($0,polygon:inner)>0.000001 }) { return false }
        func cross(_ a:[Double],_ b:[Double],_ c:[Double])->Double { (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]) }
        for i in inner.indices { for j in outer.indices {
            let p=inner[i],q=inner[(i+1)%inner.count],r=outer[j],s=outer[(j+1)%outer.count]
            if cross(p,q,r)*cross(p,q,s) < -1e-12 && cross(r,s,p)*cross(r,s,q) < -1e-12 { return false }
        } }
        return true
    }
    func canPlace(_ entity: WalkthroughEntity, entities:[WalkthroughEntity])->Bool {
        let footprint=entity.footprint()
        guard floorPolygons.contains(where:{ floor in
            Self.polygonContained(footprint,in:floor) && footprint.allSatisfy { Self.boundaryDistance($0,polygon:floor)>0.005 }
        }) else { return false }
        let other=entity.collidable ? entities.filter { $0.id != entity.id && $0.visible && $0.collidable && !["wall","floor","ceiling","wall_decor"].contains($0.kind) }.map { $0.footprint() } : []
        return !(obstacles+other).contains { Self.polygonsOverlap(footprint,$0) }
    }
    func canStand(_ p: [Double], entities: [WalkthroughEntity]) -> Bool {
        let margin=playerRadius+0.005
        guard floorPolygons.contains(where: { Self.contains(p,polygon:$0) && Self.boundaryDistance(p,polygon:$0)>margin }) else { return false }
        let dynamic=entities.filter { $0.visible && $0.collidable && !["wall","floor","ceiling","wall_decor"].contains($0.kind) }.map { $0.footprint() }
        return !(obstacles+dynamic).contains { Self.contains(p,polygon:$0) || Self.boundaryDistance(p,polygon:$0)<margin }
    }
    /// Substeps prevent tunneling through thin walls at low frame rates.
    func move(from: [Double], delta: [Double], entities: [WalkthroughEntity]) -> [Double] {
        let count=max(1,Int(ceil(hypot(delta[0],delta[1])/0.04)))
        var result=from
        for _ in 0..<min(count,256) {
            let x=[result[0]+delta[0]/Double(count),result[1]]
            if canStand(x,entities:entities) { result=x }
            let z=[result[0],result[1]+delta[1]/Double(count)]
            if canStand(z,entities:entities) { result=z }
        }
        return result
    }
}

struct WalkthroughBundle: Codable, Sendable {
    var schemaVersion: Int
    var captureId: String
    var sceneId: String
    var reconstructionRevision: Int
    var designRevision: Int
    var coordinateSystem: String
    var entities: [WalkthroughEntity]
    var materials: [WalkthroughMaterial]
    var navigation: WalkthroughNavigation
    var qualityFilename: String
    var provenanceFilename: String
    var ready: Bool

    static func safeName(_ value: String) -> Bool {
        !value.isEmpty && value.count<=128 && !value.contains("..") && value.utf8.allSatisfy {
            (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || [45,46,95].contains($0)
        }
    }
    func validate(captureId: String, revision: Int, assets: Set<String>) throws {
        guard ready, schemaVersion==2, self.captureId==captureId, reconstructionRevision==revision,
              designRevision>=0, coordinateSystem=="arkit_scan_meters_y_up", (1...512).contains(entities.count),
              Set(entities.map(\.id)).count==entities.count, Set(materials.map(\.id)).count==materials.count,
              assets.contains(qualityFilename), assets.contains(provenanceFilename) else { throw ClientError.invalidResponse }
        let byId=Dictionary(uniqueKeysWithValues: entities.map { ($0.id,$0) })
        let bindings=Dictionary(uniqueKeysWithValues: materials.map { ($0.id,$0) })
        for e in entities {
            guard Self.safeName(e.id), Self.safeName(e.asset), e.asset.hasSuffix(".obj"), assets.contains(e.asset),
                  ["wall","floor","ceiling","fixed","furniture","wall_decor"].contains(e.kind),
                  e.boundsMin.count==3, e.boundsMax.count==3, (e.boundsMin+e.boundsMax).allSatisfy(\.isFinite),
                  zip(e.boundsMin,e.boundsMax).allSatisfy({ $0.0 <= $0.1 }),
                  e.localToScanTransform.count==16, e.localToScanTransform.allSatisfy(\.isFinite),
                  !e.materialIds.isEmpty, (0...1).contains(e.observedFraction),
                  e.movable ? e.moveReady : !e.moveReady else { throw ClientError.invalidResponse }
            let m=e.localToScanTransform
            guard abs(m[3])+abs(m[7])+abs(m[11])+abs(m[15]-1)<0.001 else { throw ClientError.invalidResponse }
            for a in 0..<3 { for b in 0..<3 {
                let dot=(0..<3).reduce(0.0) { $0+m[a*4+$1]*m[b*4+$1] }
                guard abs(dot-(a==b ? 1:0))<0.002 else { throw ClientError.invalidResponse }
            } }
            let determinant=m[0]*(m[5]*m[10]-m[9]*m[6])-m[4]*(m[1]*m[10]-m[9]*m[2])+m[8]*(m[1]*m[6]-m[5]*m[2])
            guard abs(determinant-1)<0.002 else { throw ClientError.invalidResponse }
            for id in e.materialIds { guard bindings[id]?.ownerId==e.id else { throw ClientError.invalidResponse } }
            if e.kind=="wall_decor" { guard let support=e.supportId, byId[support]?.kind=="wall" else { throw ClientError.invalidResponse } }
        }
        for m in materials {
            guard byId[m.ownerId] != nil, m.baseColor.count==3, m.baseColor.allSatisfy({ $0.isFinite && (0...1).contains($0) }),
                  m.repeatMeters.isFinite, (0.01...10).contains(m.repeatMeters) else { throw ClientError.invalidResponse }
        }
        let n=navigation
        guard (1...64).contains(n.floorPolygons.count), n.obstacles.count<=4096,
              n.spawnPosition.count==3, n.spawnPosition.allSatisfy(\.isFinite), n.spawnYaw.isFinite,
              n.floorHeight.isFinite, (0.5...2.2).contains(n.eyeHeight), (0.1...0.5).contains(n.playerRadius),
              abs(n.spawnPosition[1]-n.floorHeight-n.eyeHeight)<0.01 else { throw ClientError.invalidResponse }
        for p in n.floorPolygons+n.obstacles {
            guard (3...4096).contains(p.count), p.allSatisfy({ $0.count==2 && $0.allSatisfy(\.isFinite) }),
                  !PolygonTriangulation.indices(p.map { $0.map(Float.init) }).isEmpty else { throw ClientError.invalidResponse }
        }
        guard n.canStand([n.spawnPosition[0],n.spawnPosition[2]],entities:entities) else { throw ClientError.invalidResponse }
    }

    func validateFiles(in directory: URL, assets: Set<String>) throws {
        for name in assets where name.hasSuffix(".obj") || name.hasSuffix(".mtl") {
            let lines=try String(contentsOf:directory.appendingPathComponent(name),encoding:.utf8).split(separator:"\n")
            for line in lines {
                let tokens=line.split(whereSeparator: { $0==" " || $0=="\t" }).map(String.init)
                guard let tag=tokens.first else { continue }
                if tag=="mtllib" || tag.lowercased().hasPrefix("map_") || ["bump","disp","decal","refl"].contains(tag.lowercased()) {
                    guard tokens.count>=2, (tag=="mtllib" || tokens.count==2), tokens.dropFirst().allSatisfy({ Self.safeName($0) && assets.contains($0) }) else { throw ClientError.invalidResponse }
                }
            }
        }
        let quality=try JSONSerialization.jsonObject(with:Data(contentsOf:directory.appendingPathComponent(qualityFilename))) as? [String:Any]
        guard quality?["ready"] as? Bool == true, quality?["capture_id"] as? String == captureId else { throw ClientError.invalidResponse }
    }
}
