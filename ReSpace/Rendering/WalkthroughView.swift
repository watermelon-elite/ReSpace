import ModelIO
import Combine
import SceneKit
import SceneKit.ModelIO
import SwiftUI
import UIKit

private actor WalkthroughLoader {
    func load(_ bundle: WalkthroughBundle, directory: URL) throws -> SCNScene {
        let scene=SCNScene()
        let generated=bundle.sceneId.hasPrefix("astra-")
        if generated {
            scene.background.contents=UIColor(white:0.12,alpha:1)
            let ambient=SCNNode();ambient.light=SCNLight();ambient.light?.type = .ambient
            ambient.light?.intensity=500;scene.rootNode.addChildNode(ambient)
            let sun=SCNNode();sun.light=SCNLight();sun.light?.type = .directional
            sun.light?.intensity=900;sun.eulerAngles=SCNVector3(-0.7,-0.5,0)
            scene.rootNode.addChildNode(sun)
        }
        var count=0
        for entity in bundle.entities {
            let asset=MDLAsset(url:directory.appendingPathComponent(entity.asset)); asset.loadTextures()
            let imported=SCNScene(mdlAsset:asset)
            let root=SCNNode();root.name=entity.id
            for child in imported.rootNode.childNodes {
                child.enumerateHierarchy { node,_ in
                    if let geometry=node.geometry {
                        count += geometry.elements.reduce(0) { $0+$1.primitiveCount }
                        geometry.materials.forEach { material in
                            material.lightingModel = generated ? .physicallyBased : .constant
                            material.isDoubleSided=true
                            if generated, let binding=bundle.materials.first(where:{ $0.ownerId==entity.id && $0.sourceMaterial==material.name }) {
                                material.roughness.contents=binding.roughness ?? 0.7
                                material.metalness.contents=binding.metallic ?? 0
                            }
                        }
                    }
                }
                root.addChildNode(child)
            }
            guard !root.childNodes.isEmpty else { throw ClientError.invalidGeometry }
            scene.rootNode.addChildNode(root)
        }
        guard count>0, count<=1_000_000 else { throw ClientError.invalidGeometry }
        return scene
    }
}

@MainActor private final class WalkthroughSession: ObservableObject {
    @Published var scene: SCNScene?
    @Published var bundle: WalkthroughBundle?
    @Published var selection: String?
    @Published var message: String?
    @Published var canUndo=false
    @Published var detailSummary: String?
    let camera=SCNNode()
    var position=[0.0,0.0]
    var yaw=0.0, pitch=0.0
    private var source: WalkthroughBundle?
    private var history: [WalkthroughBundle]=[]
    private var stateURL: URL?
    private var captured: [ObjectIdentifier:(Any?,SCNMatrix4,SCNWrapMode,SCNWrapMode)]=[:]

    var selected: WalkthroughEntity? { bundle?.entities.first { $0.id==selection } }
    func load(_ url: URL) async throws {
        let data=try Data(contentsOf:url)
        let original=try Wire.decoder().decode(WalkthroughBundle.self,from:data)
        let directory=url.deletingLastPathComponent()
        let assets=Set(try FileManager.default.contentsOfDirectory(atPath:directory.path))
        try original.validate(captureId:original.captureId,revision:original.reconstructionRevision,assets:assets)
        try original.validateFiles(in:directory,assets:assets)
        if let quality=try JSONSerialization.jsonObject(with:Data(contentsOf:directory.appendingPathComponent(original.qualityFilename))) as? [String:Any],
           let objects=quality["objects"] as? [[String:Any]], !objects.isEmpty {
            let detailed=objects.filter { $0["detail"] as? String == "detailed" }.count
            detailSummary="\(detailed) of \(objects.count) items received detailed geometry"
        }
        source=original
        stateURL=directory.deletingLastPathComponent().appendingPathComponent("design-\(original.reconstructionRevision).json")
        var selected=original
        if let stateURL,FileManager.default.fileExists(atPath:stateURL.path) {
            do {
                let saved=try Wire.decoder().decode(WalkthroughBundle.self,from:Data(contentsOf:stateURL))
                try saved.validate(captureId:original.captureId,revision:original.reconstructionRevision,assets:assets)
                var nav=saved.navigation;nav.spawnPosition=original.navigation.spawnPosition;nav.spawnYaw=original.navigation.spawnYaw
                guard saved.sceneId==original.sceneId, saved.entities.count==original.entities.count,
                      try Wire.encoder().encode(nav)==Wire.encoder().encode(original.navigation) else { throw ClientError.invalidResponse }
                for entity in saved.entities {
                    guard let prior=original.entities.first(where: { $0.id==entity.id }), prior.asset==entity.asset,
                          prior.kind==entity.kind, prior.boundsMin==entity.boundsMin, prior.boundsMax==entity.boundsMax,
                          prior.supportId==entity.supportId, prior.materialIds==entity.materialIds,
                          prior.surfacePolygons==entity.surfacePolygons, prior.surfaceHoles==entity.surfaceHoles,
                          prior.movable || prior.localToScanTransform==entity.localToScanTransform && prior.visible==entity.visible else { throw ClientError.invalidResponse }
                }
                selected=saved
            } catch { message="Saved changes could not be restored. The captured room is available." }
        }
        let loaded=try await WalkthroughLoader().load(original,directory:directory)
        try Task.checkCancellation()
        camera.camera=SCNCamera();camera.camera?.zNear=0.03;camera.camera?.zFar=100
        if original.sceneId.hasPrefix("astra-") {
            camera.camera?.screenSpaceAmbientOcclusionIntensity=0.65
            camera.camera?.screenSpaceAmbientOcclusionRadius=0.15
            camera.camera?.wantsHDR=true
        }
        loaded.rootNode.addChildNode(camera)
        bundle=selected;scene=loaded;reset();apply()
    }
    func reset() {
        guard let nav=bundle?.navigation else { return }
        position=[nav.spawnPosition[0],nav.spawnPosition[2]];yaw=nav.spawnYaw;pitch=0;updateCamera()
    }
    func look(x: Double,y: Double) { yaw-=x*0.004;pitch=max(-1.3,min(1.3,pitch-y*0.004));updateCamera() }
    func walk(x: Double,z: Double) {
        guard let bundle else { return }
        let delta=[cos(yaw)*x+sin(yaw)*z,-sin(yaw)*x+cos(yaw)*z]
        position=bundle.navigation.move(from:position,delta:delta,entities:bundle.entities)
        updateCamera()
    }
    private func updateCamera() {
        guard let nav=bundle?.navigation else { return }
        camera.position=SCNVector3(Float(position[0]),Float(nav.floorHeight+nav.eyeHeight),Float(position[1]))
        camera.eulerAngles=SCNVector3(Float(pitch),Float(yaw),0)
    }
    func select(_ node: SCNNode) {
        var current: SCNNode?=node
        while let value=current {
            if bundle?.entities.contains(where: { $0.id==value.name })==true { selection=value.name;return }
            current=value.parent
        }
    }
    private func commit(_ value: WalkthroughBundle) throws {
        guard let prior=bundle,let stateURL else { return }
        var value=value;value.designRevision=prior.designRevision+1
        guard value.navigation.canStand(position,entities:value.entities) else { throw ClientError.storage("That position is too close to you.") }
        value.navigation.spawnPosition=[position[0],value.navigation.floorHeight+value.navigation.eyeHeight,position[1]]
        value.navigation.spawnYaw=yaw
        try Wire.encoder().encode(value).write(to:stateURL,options:.atomic)
        history.append(prior);if history.count>20 { history.removeFirst() }
        canUndo=true;bundle=value;apply()
    }
    func undo() {
        guard let previous=history.last,let stateURL else { return }
        do {
            try Wire.encoder().encode(previous).write(to:stateURL,options:.atomic)
            history.removeLast();canUndo = !history.isEmpty;bundle=previous;reset();apply()
        } catch { message=error.localizedDescription }
    }
    func restore() {
        guard let source else { return }
        let previous=position,oldYaw=yaw
        position=[source.navigation.spawnPosition[0],source.navigation.spawnPosition[2]];yaw=source.navigation.spawnYaw
        do { try commit(source);selection=nil;updateCamera() }
        catch { position=previous;yaw=oldYaw;updateCamera();message=error.localizedDescription }
    }
    func rotateSelected() {
        guard var value=bundle,let index=value.entities.firstIndex(where: { $0.id==selection }),value.entities[index].kind=="furniture" else { return }
        let original=value.entities[index]
        var result=original
        for step in 1...9 {
            let angle=Double(step)*Double.pi/18
            var rotated=original
            for column in 0..<3 {
                let x=original.localToScanTransform[column*4],z=original.localToScanTransform[column*4+2]
                rotated.localToScanTransform[column*4]=cos(angle)*x+sin(angle)*z
                rotated.localToScanTransform[column*4+2] = -sin(angle)*x+cos(angle)*z
            }
            guard value.navigation.canPlace(rotated,entities:value.entities) else { message="There is not enough clear space to rotate this item.";return }
            result=rotated
        }
        value.entities[index]=result
        do { try commit(value) } catch { message=error.localizedDescription }
    }
    func removeSelected() {
        guard var value=bundle, let index=value.entities.firstIndex(where: { $0.id==selection }),value.entities[index].movable else { return }
        value.entities[index].visible=false
        do { try commit(value);selection=nil } catch { message=error.localizedDescription }
    }
    func moveSelected(x: Double,y: Double) {
        guard var value=bundle,let index=value.entities.firstIndex(where: { $0.id==selection }),value.entities[index].movable else { return }
        var entity=value.entities[index]
        if entity.kind=="wall_decor",let wall=value.entities.first(where: { $0.id==entity.supportId }) {
            let m=wall.localToScanTransform
            for r in 0..<3 { entity.localToScanTransform[12+r]+=m[r]*x+m[4+r]*y }
            let center=[entity.localToScanTransform[12],entity.localToScanTransform[13],entity.localToScanTransform[14]]
            let local=(0..<3).map { axis in (0..<3).reduce(0.0) { $0+m[axis*4+$1]*(center[$1]-m[12+$1]) } }
            let halfX=(entity.boundsMax[0]-entity.boundsMin[0])/2,halfY=(entity.boundsMax[1]-entity.boundsMin[1])/2
            guard local[0]-halfX>=wall.boundsMin[0],local[0]+halfX<=wall.boundsMax[0],local[1]-halfY>=wall.boundsMin[1],local[1]+halfY<=wall.boundsMax[1] else { message="Keep this item on its wall.";return }
            let rectangle=[[local[0]-halfX,local[1]-halfY],[local[0]+halfX,local[1]-halfY],[local[0]+halfX,local[1]+halfY],[local[0]-halfX,local[1]+halfY]]
            if let regions=wall.surfacePolygons,!regions.isEmpty {
                guard regions.contains(where:{ WalkthroughNavigation.polygonContained(rectangle,in:$0) }),
                      !(wall.surfaceHoles ?? []).contains(where:{ WalkthroughNavigation.polygonsOverlap(rectangle,$0) }) else { message="Keep this item on a clear part of the wall.";return }
            }
        } else {
            entity.localToScanTransform[12]+=cos(yaw)*x-sin(yaw)*y
            entity.localToScanTransform[14] += -sin(yaw)*x-cos(yaw)*y
            let old=value.entities[index]
            for step in 1...5 {
                var intermediate=entity
                for axis in 12...14 { intermediate.localToScanTransform[axis]=old.localToScanTransform[axis]+(entity.localToScanTransform[axis]-old.localToScanTransform[axis])*Double(step)/5 }
                guard value.navigation.canPlace(intermediate,entities:value.entities) else { message="Keep this item in clear floor space.";return }
            }
        }
        value.entities[index]=entity
        do { try commit(value) } catch { message=error.localizedDescription }
    }
    func finish(_ name: String,color: UIColor = .white) {
        guard var value=bundle,let entity=selected,entity.finishReady else { return }
        var r: CGFloat=1,g: CGFloat=1,b: CGFloat=1,a: CGFloat=1;color.getRed(&r,green:&g,blue:&b,alpha:&a)
        for i in value.materials.indices where value.materials[i].ownerId==entity.id {
            value.materials[i].finish=name;value.materials[i].baseColor=[Double(r),Double(g),Double(b)]
        }
        do { try commit(value) } catch { message=error.localizedDescription }
    }
    private func apply() {
        guard let bundle,let source,let scene else { return }
        for entity in bundle.entities {
            guard let root=scene.rootNode.childNode(withName:entity.id,recursively:false) else { continue }
            let m=entity.localToScanTransform.map(Float.init)
            root.simdTransform=simd_float4x4(SIMD4(m[0],m[1],m[2],m[3]),SIMD4(m[4],m[5],m[6],m[7]),SIMD4(m[8],m[9],m[10],m[11]),SIMD4(m[12],m[13],m[14],m[15]))
            root.isHidden = !entity.visible
            root.enumerateHierarchy { node,_ in
                for material in node.geometry?.materials ?? [] {
                    guard let binding=bundle.materials.first(where: { $0.ownerId==entity.id && $0.sourceMaterial==material.name }) else { continue }
                    let key=ObjectIdentifier(material)
                    if captured[key]==nil { captured[key]=(material.diffuse.contents,material.diffuse.contentsTransform,material.diffuse.wrapS,material.diffuse.wrapT) }
                    if binding.finish=="captured" {
                        if let prior=source.materials.first(where: { $0.id==binding.id }), prior.finish=="captured" {
                            // Original diffuse contents are retained on the material.
                            if let original=captured[key] {
                                material.diffuse.contents=original.0;material.diffuse.contentsTransform=original.1
                                material.diffuse.wrapS=original.2;material.diffuse.wrapT=original.3
                            }
                        }
                    } else {
                        let color=UIColor(red:binding.baseColor[0],green:binding.baseColor[1],blue:binding.baseColor[2],alpha:1)
                        if binding.finish=="paint" { material.diffuse.contents=color }
                        else {
                            let image=UIGraphicsImageRenderer(size:CGSize(width:128,height:128)).image { context in
                                color.setFill();context.fill(CGRect(x:0,y:0,width:128,height:128))
                                UIColor(white:0.35,alpha:0.6).setStroke()
                                let path=UIBezierPath();path.lineWidth=2
                                path.move(to:.zero);path.addLine(to:CGPoint(x:128,y:0))
                                path.move(to:.zero);path.addLine(to:CGPoint(x:0,y:128))
                                if binding.finish=="wallpaper" { path.move(to:CGPoint(x:0,y:64));path.addLine(to:CGPoint(x:128,y:64)) };path.stroke()
                            }
                            material.diffuse.contents=image;material.diffuse.wrapS = .repeat;material.diffuse.wrapT = .repeat
                            let width=max(entity.boundsMax[0]-entity.boundsMin[0],0.01)
                            let height=max(entity.boundsMax[1]-entity.boundsMin[1],0.01)
                            material.diffuse.contentsTransform=SCNMatrix4MakeScale(Float(width/binding.repeatMeters),Float(height/binding.repeatMeters),1)
                        }
                    }
                }
            }
        }
    }
}

struct WalkthroughView: View {
    let sceneURL: URL
    @StateObject private var session=WalkthroughSession()
    @State private var error: String?
    @State private var paint=Color.white
    var body: some View {
        ZStack {
            if let scene=session.scene {
                WalkthroughCanvas(scene:scene,session:session).ignoresSafeArea(edges:.bottom)
                VStack {
                    HStack { Button("Reset view") { session.reset() };Spacer();Button("Undo") { session.undo() }.disabled(!session.canUndo);Button("Restore room") { session.restore() } }.buttonStyle(.bordered).padding().background(.regularMaterial)
                    if let summary=session.detailSummary { Text(summary).font(.caption).padding(6).background(.regularMaterial) }
                    Spacer()
                    if let entity=session.selected {
                        VStack(spacing:8) {
                            Text(entity.label).font(.headline)
                            if entity.movable {
                                HStack { Button("←") { session.moveSelected(x:-0.15,y:0) };Button("↑") { session.moveSelected(x:0,y:0.15) };Button("↓") { session.moveSelected(x:0,y:-0.15) };Button("→") { session.moveSelected(x:0.15,y:0) };Button("Remove",role:.destructive) { session.removeSelected() } }
                                if entity.kind=="furniture" { Button("Rotate") { session.rotateSelected() } }
                            }
                            if entity.finishReady {
                                HStack { ColorPicker("Color",selection:$paint);Button("Paint") { session.finish("paint",color:UIColor(paint)) };Button("Tile") { session.finish("tile",color:UIColor(paint)) };Button("Wallpaper") { session.finish("wallpaper",color:UIColor(paint)) };Button("Original") { session.finish("captured") } }.font(.caption)
                            }
                            Button("Done") { session.selection=nil }
                        }.padding().background(.regularMaterial,in:RoundedRectangle(cornerRadius:16)).padding()
                    }
                    HStack { Button("◀") { session.walk(x:-0.15,z:0) };Button("Forward") { session.walk(x:0,z:-0.15) };Button("Back") { session.walk(x:0,z:0.15) };Button("▶") { session.walk(x:0.15,z:0) } }.buttonRepeatBehavior(.enabled).buttonStyle(.borderedProminent).padding().background(.regularMaterial)
                    Text("Drag to look · Hold a walking control to move · Tap to select").font(.caption).padding(6).background(.regularMaterial)
                }
            } else if let error { ContentUnavailableView("Walkthrough unavailable",systemImage:"cube",description:Text(error)) }
            else { ProgressView("Opening your room…") }
        }
        .task(id:sceneURL) { do { try await session.load(sceneURL) } catch is CancellationError {} catch { self.error=error.localizedDescription } }
        .alert("Room",isPresented:Binding(get:{ session.message != nil },set:{ if !$0 { session.message=nil } })) { Button("OK") { session.message=nil } } message: { Text(session.message ?? "") }
    }
}

private struct WalkthroughCanvas: UIViewRepresentable {
    let scene: SCNScene
    let session: WalkthroughSession
    func makeUIView(context:Context) -> SCNView {
        let view=SCNView();view.scene=scene;view.pointOfView=session.camera;view.allowsCameraControl=false
        view.antialiasingMode = .multisampling4X;view.preferredFramesPerSecond=30
        view.addGestureRecognizer(UIPanGestureRecognizer(target:context.coordinator,action:#selector(Coordinator.pan(_:))))
        view.addGestureRecognizer(UITapGestureRecognizer(target:context.coordinator,action:#selector(Coordinator.tap(_:))))
        return view
    }
    func updateUIView(_ view:SCNView,context:Context) { view.scene=scene;view.pointOfView=session.camera }
    func makeCoordinator() -> Coordinator { Coordinator(session) }
    @MainActor final class Coordinator: NSObject {
        let session: WalkthroughSession
        init(_ session:WalkthroughSession) { self.session=session }
        @objc func pan(_ gesture:UIPanGestureRecognizer) {
            let delta=gesture.translation(in:gesture.view);gesture.setTranslation(.zero,in:gesture.view)
            session.look(x:delta.x,y:delta.y)
        }
        @objc func tap(_ gesture:UITapGestureRecognizer) {
            guard let view=gesture.view as? SCNView,let hit=view.hitTest(gesture.location(in:view),options:nil).first else { return }
            session.select(hit.node)
        }
    }
}
