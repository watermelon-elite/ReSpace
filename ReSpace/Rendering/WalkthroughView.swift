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
        var textures: [String:UIImage]=[:]
        for name in Set(bundle.materials.flatMap { [$0.baseColorTexture,$0.roughnessTexture,$0.normalTexture].compactMap { $0 } }) {
            guard let image=UIImage(contentsOfFile:directory.appendingPathComponent(name).path) else { throw ClientError.invalidResponse }
            textures[name]=image
        }
        var roughnessMaps: [String:UIImage]=[:]
        for binding in bundle.materials {
            guard let name=binding.roughnessTexture, let pattern=textures[name] else { continue }
            let key="\(name):\(binding.roughness ?? 0.7)"
            guard roughnessMaps[key]==nil else { continue }
            let format=UIGraphicsImageRendererFormat();format.scale=1;format.opaque=true
            roughnessMaps[key]=UIGraphicsImageRenderer(size:pattern.size,format:format).image { context in
                UIColor(white:binding.roughness ?? 0.7,alpha:1).setFill()
                context.fill(CGRect(origin:.zero,size:pattern.size))
                pattern.draw(in:CGRect(origin:.zero,size:pattern.size),blendMode:.multiply,alpha:1)
            }
        }
        var count=0
        for entity in bundle.entities {
            let asset=MDLAsset(url:directory.appendingPathComponent(entity.asset)); asset.loadTextures()
            if bundle.materials.contains(where:{ $0.ownerId==entity.id && $0.normalTexture != nil }) {
                for mesh in asset.childObjects(of:MDLMesh.self) as? [MDLMesh] ?? [] {
                    if mesh.vertexAttributeData(forAttributeNamed:MDLVertexAttributeNormal)==nil {
                        mesh.addNormals(withAttributeNamed:MDLVertexAttributeNormal,creaseThreshold:0.5)
                    }
                    mesh.addOrthTanBasis(forTextureCoordinateAttributeNamed:MDLVertexAttributeTextureCoordinate,
                        normalAttributeNamed:MDLVertexAttributeNormal,tangentAttributeNamed:MDLVertexAttributeTangent)
                }
            }
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
                                if let name=binding.baseColorTexture, let texture=textures[name] {
                                    material.diffuse.contents=texture
                                    material.multiply.contents=UIColor(red:binding.baseColor[0],green:binding.baseColor[1],blue:binding.baseColor[2],alpha:1)
                                }
                                if let name=binding.roughnessTexture {
                                    material.roughness.contents=roughnessMaps["\(name):\(binding.roughness ?? 0.7)"]
                                    material.roughness.intensity=1
                                }
                                if let name=binding.normalTexture { material.normal.contents=textures[name] }
                                for property in [material.diffuse,material.normal,material.roughness] {
                                    property.wrapS = .repeat;property.wrapT = .repeat
                                    property.minificationFilter = .linear;property.magnificationFilter = .linear;property.mipFilter = .linear
                                }
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
    private struct OriginalMaterial {
        let diffuse: Any?
        let transform: SCNMatrix4
        let wrapS: SCNWrapMode
        let wrapT: SCNWrapMode
        let multiply: Any?
        let normal: Any?
        let roughness: Any?
        let roughnessIntensity: CGFloat
    }
    @Published var scene: SCNScene?
    @Published var bundle: WalkthroughBundle?
    @Published var selection: String?
    @Published var message: String?
    @Published var detailSummary: String?
    let camera=SCNNode()
    var position=[0.0,0.0]
    var yaw=0.0, pitch=0.0
    private var source: WalkthroughBundle?
    private var captured: [ObjectIdentifier:OriginalMaterial]=[:]

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
        let loaded=try await WalkthroughLoader().load(original,directory:directory)
        try Task.checkCancellation()
        camera.camera=SCNCamera();camera.camera?.zNear=0.03;camera.camera?.zFar=100
        if original.sceneId.hasPrefix("astra-") {
            camera.camera?.screenSpaceAmbientOcclusionIntensity=0.65
            camera.camera?.screenSpaceAmbientOcclusionRadius=0.15
            camera.camera?.wantsHDR=true
        }
        loaded.rootNode.addChildNode(camera)
        bundle=original;scene=loaded;reset();apply()
    }
    func reset() {
        guard let nav=bundle?.navigation else { return }
        position=[nav.spawnPosition[0],nav.spawnPosition[2]];yaw=nav.spawnYaw;pitch=0;updateCamera()
    }
    func renditionInput(directory: URL) throws -> RoomRenditionInput {
        guard let scene, var design=bundle, let source else { throw ClientError.invalidGeometry }
        // Keep one corner perspective regardless of where the user walks.
        // The image uses the verified reconstruction without local design edits.
        design.navigation=source.navigation
        let key=try ReconstructionClient.renditionKey(design)
        let url=directory.appendingPathComponent("rendition-\(key).png")
        let viewCamera=camera.clone()
        viewCamera.camera=camera.camera?.copy() as? SCNCamera
        guard let view=RoomRenditionCamera.cornerView(navigation:source.navigation,entities:design.entities) else {
            throw ClientError.storage("There is no clear corner for a room image in this layout.")
        }
        viewCamera.position=SCNVector3(Float(view.position[0]),Float(view.position[1]),Float(view.position[2]))
        viewCamera.look(at:SCNVector3(Float(view.target[0]),Float(view.target[1]),Float(view.target[2])))
        viewCamera.camera?.fieldOfView=70
        let renderer=SCNRenderer(device:nil,options:nil)
        renderer.scene=scene;renderer.pointOfView=viewCamera
        let size=CGSize(width:1536,height:1024)
        let snapshot=renderer.snapshot(atTime:0,with:size,antialiasingMode:.multisampling4X)
        let format=UIGraphicsImageRendererFormat();format.scale=1;format.opaque=true
        let image=UIGraphicsImageRenderer(size:size,format:format).image { _ in
            snapshot.draw(in:CGRect(origin:.zero,size:size))
        }
        guard let jpeg=image.jpegData(compressionQuality:0.9) else { throw ClientError.invalidResponse }
        return RoomRenditionInput(id:key,scene:design,image:jpeg,cachedURL:url)
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
                    if captured[key]==nil {
                        captured[key]=OriginalMaterial(diffuse:material.diffuse.contents,transform:material.diffuse.contentsTransform,
                            wrapS:material.diffuse.wrapS,wrapT:material.diffuse.wrapT,multiply:material.multiply.contents,
                            normal:material.normal.contents,roughness:material.roughness.contents,roughnessIntensity:material.roughness.intensity)
                    }
                    if binding.finish=="captured" {
                        if let prior=source.materials.first(where: { $0.id==binding.id }), prior.finish=="captured" {
                            // Original diffuse contents are retained on the material.
                            if let original=captured[key] {
                                material.diffuse.contents=original.diffuse;material.diffuse.contentsTransform=original.transform
                                material.diffuse.wrapS=original.wrapS;material.diffuse.wrapT=original.wrapT
                                material.multiply.contents=original.multiply;material.normal.contents=original.normal
                                material.roughness.contents=original.roughness;material.roughness.intensity=original.roughnessIntensity
                            }
                        }
                    } else {
                        material.multiply.contents=UIColor.white;material.normal.contents=nil
                        material.roughness.contents=binding.roughness ?? 0.7;material.roughness.intensity=1
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
    var reconstruction: ReconstructionClient? = nil
    @StateObject private var session=WalkthroughSession()
    @State private var error: String?
    @State private var rendition: RoomRenditionInput?
    var body: some View {
        ZStack {
            if let scene=session.scene {
                WalkthroughCanvas(scene:scene,session:session).ignoresSafeArea(edges:.bottom)
                VStack {
                    HStack { Spacer(); RSIconButton(symbol: "viewfinder", label: "Reset View") { session.reset() } }.padding(.horizontal, 16).background(.white)
                    if let summary=session.detailSummary { Text(summary).font(ReSpaceStyle.font(13)).padding(6).background(.regularMaterial) }
                    if reconstruction != nil {
                        Button {
                            do { rendition=try session.renditionInput(directory:sceneURL.deletingLastPathComponent()) }
                            catch { session.message=error.localizedDescription }
                        } label: { Label("Create realistic image",systemImage:"camera.aperture") }
                        .buttonStyle(RSButtonStyle(kind: .secondary))
                    }
                    Spacer()
                    if let entity=session.selected {
                        VStack(spacing:8) {
                            Text(entity.label).font(ReSpaceStyle.font(18, weight: .semibold))
                            Button("Done") { session.selection=nil }
                        }.padding().background(.regularMaterial,in:RoundedRectangle(cornerRadius:16)).padding()
                    }
                    HStack { Button { session.walk(x:-0.15,z:0) } label: { Image(systemName: "arrow.left") }.accessibilityLabel("Walk left");Button("Forward") { session.walk(x:0,z:-0.15) };Button("Back") { session.walk(x:0,z:0.15) };Button { session.walk(x:0.15,z:0) } label: { Image(systemName: "arrow.right") }.accessibilityLabel("Walk right") }.buttonRepeatBehavior(.enabled).buttonStyle(RSButtonStyle(kind: .secondary)).padding().background(.regularMaterial)
                    Text("Drag to look · Hold a walking control to move · Tap to select").font(ReSpaceStyle.font(13)).padding(6).background(.regularMaterial)
                }
            } else if let error { ContentUnavailableView("Walkthrough unavailable",systemImage:"cube",description:Text(error)) }
            else { ProgressView("Opening your room…") }
        }
        .task(id:sceneURL) { do { try await session.load(sceneURL) } catch is CancellationError {} catch { self.error=error.localizedDescription } }
        .sheet(item:$rendition) { input in
            if let reconstruction { RoomRenditionView(input:input,client:reconstruction) }
        }
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
