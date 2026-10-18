import Foundation

/// A repeatable interior photograph, independent of the walkthrough camera.
struct RoomRenditionCamera: Equatable, Sendable {
    static let viewID = "corner_room_view_v2"
    let position: [Double]
    let target: [Double]

    static func cornerView(navigation: WalkthroughNavigation, entities: [WalkthroughEntity]) -> Self? {
        func signedArea(_ polygon: [[Double]]) -> Double {
            polygon.indices.reduce(0) { sum, i in
                let a=polygon[i], b=polygon[(i+1)%polygon.count]
                return sum+a[0]*b[1]-b[0]*a[1]
            }
        }
        let spawn=[navigation.spawnPosition[0],navigation.spawnPosition[2]]
        let rooms=navigation.floorPolygons.filter { WalkthroughNavigation.contains(spawn,polygon:$0) }
        guard var floor=(rooms.isEmpty ? navigation.floorPolygons : rooms).max(by: {
            abs(signedArea($0)) < abs(signedArea($1))
        }) else { return nil }
        if floor.first == floor.last { floor.removeLast() }
        let area=signedArea(floor)
        guard floor.count>=3, abs(area)>0.000001 else { return nil }
        var center=[0.0,0.0]
        for i in floor.indices {
            let a=floor[i], b=floor[(i+1)%floor.count], cross=a[0]*b[1]-b[0]*a[1]
            for axis in 0..<2 { center[axis] += (a[axis]+b[axis])*cross/(3*area) }
        }
        // A concave room's centroid may fall outside its measured outline.
        // Use the nearest interior triangle center in that case.
        if !WalkthroughNavigation.contains(center,polygon:floor) {
            let triangles=PolygonTriangulation.indices(floor.map { $0.map(Float.init) })
            let interior=stride(from:0,to:triangles.count,by:3).map { i in
                (0..<2).map { axis in (0..<3).reduce(0.0) { $0+floor[Int(triangles[i+$1])][axis]/3 } }
            }
            guard let point=interior.min(by: { hypot($0[0]-center[0],$0[1]-center[1]) < hypot($1[0]-center[0],$1[1]-center[1]) }) else { return nil }
            center=point
        }
        // Only convex vertices are room corners. Ignore collinear outline
        // samples and sort deterministically, preferring a broad diagonal view.
        let corners=floor.indices.filter { i in
            let a=floor[(i+floor.count-1)%floor.count], b=floor[i], c=floor[(i+1)%floor.count]
            return ((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))*area > 0.000001
        }.sorted {
            let a=hypot(floor[$0][0]-center[0],floor[$0][1]-center[1]), b=hypot(floor[$1][0]-center[0],floor[$1][1]-center[1])
            if abs(a-b)>0.000001 { return a>b }
            return floor[$0][0] == floor[$1][0] ? floor[$0][1]<floor[$1][1] : floor[$0][0]<floor[$1][0]
        }
        // Inset from real corners so the camera is inside both walls and clear
        // of furniture. Try other corners before moving further into the room.
        for inset in [0.5,0.7,0.9,1.1,1.3,1.5,0.35] {
            for i in corners {
                let corner=floor[i], previous=floor[(i+floor.count-1)%floor.count], next=floor[(i+1)%floor.count]
                let a=hypot(previous[0]-corner[0],previous[1]-corner[1]), b=hypot(next[0]-corner[0],next[1]-corner[1])
                guard a>0.000001, b>0.000001 else { continue }
                // The inward bisector clears both walls even in long, narrow
                // rooms where the center-facing ray runs almost along a wall.
                let dx=(previous[0]-corner[0])/a+(next[0]-corner[0])/b
                let dz=(previous[1]-corner[1])/a+(next[1]-corner[1])/b
                let length=hypot(dx,dz), distance=hypot(center[0]-corner[0],center[1]-corner[1])
                guard inset<distance*0.5 else { continue }
                let p=[corner[0]+dx*inset/length,corner[1]+dz*inset/length]
                guard navigation.canStand(p,entities:entities) else { continue }
                // Avoid looking through an intervening wall in concave rooms.
                guard (1...20).allSatisfy({ step in
                    let t=Double(step)/20
                    return WalkthroughNavigation.contains([p[0]+(center[0]-p[0])*t,p[1]+(center[1]-p[1])*t],polygon:floor)
                }) else { continue }
                return Self(position:[p[0],navigation.floorHeight+navigation.eyeHeight,p[1]],
                            target:[center[0],navigation.floorHeight+navigation.eyeHeight*0.75,center[1]])
            }
        }
        return nil
    }
}
