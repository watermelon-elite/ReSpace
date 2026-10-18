import XCTest
import SceneKit
import ModelIO
import SceneKit.ModelIO
@testable import ReSpaceCore

final class WalkthroughTests: XCTestCase {
    func testAstraGeneratedSceneImportsWithMaterialsAndSafeFirstPersonNavigation() throws {
        guard let path=ProcessInfo.processInfo.environment["RESPACE_TEST_ASTRA_SCENE"] else {
            throw XCTSkip("Opt-in native import of the Python-produced synthetic Astra scene")
        }
        let root=URL(fileURLWithPath:path)
        let result=try Wire.decoder().decode(ReconstructionResult.self,from:Data(contentsOf:root.appendingPathComponent("completion.json")))
        try result.validate()
        XCTAssertTrue(result.isAIGenerated && result.isWalkthrough)
        let bundle=try Wire.decoder().decode(WalkthroughBundle.self,from:Data(contentsOf:root.appendingPathComponent("scene.json")))
        let assets=Set(result.assets.map(\.filename))
        try bundle.validate(captureId:"analytic-room",revision:1,assets:assets)
        try bundle.validateFiles(in:root,assets:assets)
        let spawn=bundle.navigation.spawnPosition
        XCTAssertTrue(bundle.navigation.canStand([spawn[0],spawn[2]],entities:bundle.entities))
        let walked=bundle.navigation.move(from:[1.5,1.5],delta:[8,0],entities:bundle.entities)
        XCTAssertLessThan(walked[0],1.8)
        var count=0
        for entity in bundle.entities {
            let asset=MDLAsset(url:root.appendingPathComponent(entity.asset));asset.loadTextures()
            let scene=SCNScene(mdlAsset:asset)
            let names=Set(bundle.materials.filter { $0.ownerId==entity.id }.map(\.sourceMaterial))
            var hasMaterial=false
            scene.rootNode.enumerateHierarchy { node,_ in
                if let geometry=node.geometry {
                    count += geometry.elements.reduce(0) { $0+$1.primitiveCount }
                    hasMaterial = hasMaterial || geometry.materials.contains { names.contains($0.name ?? "") && $0.diffuse.contents != nil }
                }
            }
            XCTAssertTrue(hasMaterial,"Generated material missing for \(entity.id)")
        }
        XCTAssertEqual(count,result.generatedTriangleCount)
    }

    private func fixture() throws -> (WalkthroughBundle,URL,Set<String>) {
        let root=try XCTUnwrap(Bundle.module.url(forResource:"Fixtures",withExtension:nil)).appendingPathComponent("Walkthrough")
        let bundle=try Wire.decoder().decode(WalkthroughBundle.self,from:Data(contentsOf:root.appendingPathComponent("scene.json")))
        return (bundle,root,Set(try FileManager.default.contentsOfDirectory(atPath:root.path)))
    }
    func testPythonProducedFinishedSceneLoadsWithNativeTexturesAndMetricBounds() throws {
        let (bundle,root,assets)=try fixture()
        try bundle.validate(captureId:"analytic-room",revision:1,assets:assets)
        try bundle.validateFiles(in:root,assets:assets)
        let asset=MDLAsset(url:root.appendingPathComponent("model.obj"));asset.loadTextures()
        let scene=SCNScene(mdlAsset:asset)
        var geometry=0,textured=0
        scene.rootNode.enumerateHierarchy { node,_ in
            if let mesh=node.geometry {
                geometry += 1
                textured += mesh.materials.filter { $0.diffuse.contents != nil }.count
            }
        }
        XCTAssertGreaterThan(geometry,0);XCTAssertGreaterThan(textured,0)
        let bounds=scene.rootNode.boundingBox
        XCTAssertEqual(Double(bounds.max.x-bounds.min.x),4,accuracy:0.01)
        XCTAssertEqual(Double(bounds.max.y-bounds.min.y),2.5,accuracy:0.01)
        XCTAssertEqual(Double(bounds.max.z-bounds.min.z),4,accuracy:0.01)
        for entity in bundle.entities {
            let item=MDLAsset(url:root.appendingPathComponent(entity.asset));item.loadTextures()
            let imported=SCNScene(mdlAsset:item)
            let expected=Set(bundle.materials.filter { $0.ownerId==entity.id }.map(\.sourceMaterial))
            var ownedMaterial=false,rasterTexture=false
            imported.rootNode.enumerateHierarchy { node,_ in
                for material in node.geometry?.materials ?? [] {
                    if let name=material.name,expected.contains(name) { ownedMaterial=true }
                    if let contents=material.diffuse.contents {
                        let type=String(reflecting:Swift.type(of:contents))
                        if let texture=contents as? MDLTexture {
                            if texture.dimensions.x>0 && texture.dimensions.y>0 && texture.texelDataWithTopLeftOrigin() != nil { rasterTexture=true }
                        } else if type.contains("Image") || contents is URL || contents is String { rasterTexture=true }
                    }
                }
            }
            XCTAssertTrue(ownedMaterial,"Native material ownership was lost for \(entity.id)")
            XCTAssertTrue(rasterTexture,"Native captured texture was lost for \(entity.id)")
        }
    }
    func testWalkingDoesNotTunnelThroughWallsOrFurniture() throws {
        let (bundle,_,_)=try fixture()
        let navigation=bundle.navigation
        let blocked=navigation.move(from:[0,1.5],delta:[0,-4],entities:bundle.entities)
        XCTAssertGreaterThan(blocked[1],0.1) // Chair extends to z=-0.1, plus player radius.
        let boundary=navigation.move(from:[1.5,1.5],delta:[8,0],entities:bundle.entities)
        XCTAssertLessThan(boundary[0],1.81)
        var removed=bundle.entities
        removed[0].visible=false
        let clear=navigation.move(from:[0,1.5],delta:[0,-2.5],entities:removed)
        XCTAssertLessThan(clear[1],-0.9)
    }
    func testFixedGeometryAndUnfinishedResultsCannotBecomeWalkthroughs() throws {
        var (bundle,_,assets)=try fixture()
        let index=try XCTUnwrap(bundle.entities.firstIndex(where:{ $0.kind=="wall" }))
        bundle.entities[index].moveReady=true
        XCTAssertThrowsError(try bundle.validate(captureId:"analytic-room",revision:1,assets:assets))
        var result=try Wire.decoder().decode(ReconstructionResult.self,from:Data(contentsOf:fixture().1.appendingPathComponent("completion.json")))
        try result.validate()
        result.status="partially_processed"
        XCTAssertThrowsError(try result.validate())
    }
    func testCrossingRectanglesCollideEvenWithoutContainedCorners() {
        let horizontal=[[-2.0,-0.1],[2,-0.1],[2,0.1],[-2,0.1]]
        let vertical=[[-0.1,-2.0],[0.1,-2],[0.1,2],[-0.1,2]]
        XCTAssertTrue(WalkthroughNavigation.polygonsOverlap(horizontal,vertical))
    }
    func testDecorCannotBridgeDoorOpeningEvenIfAllCornersAreOnWall() {
        let wall=[[-2.0,0],[-0.5,0],[-0.5,2],[0.5,2],[0.5,0],[2,0],[2,3],[-2,3]]
        let poster=[[-0.75,1.0],[0.75,1],[0.75,2.5],[-0.75,2.5]]
        XCTAssertTrue(poster.allSatisfy { WalkthroughNavigation.contains($0,polygon:wall) })
        XCTAssertFalse(WalkthroughNavigation.polygonContained(poster,in:wall))
    }
    func testMaterialOwnerAndSceneRevisionRemainBoundToCapture() throws {
        var (bundle,_,assets)=try fixture()
        XCTAssertThrowsError(try bundle.validate(captureId:"other-capture",revision:1,assets:assets))
        XCTAssertThrowsError(try bundle.validate(captureId:"analytic-room",revision:2,assets:assets))
        bundle.materials[0].ownerId="unknown-owner"
        XCTAssertThrowsError(try bundle.validate(captureId:"analytic-room",revision:1,assets:assets))
    }
    func testDetailedGeometryBudgetAndMaterialParametersAreValidated() throws {
        var (bundle,root,assets)=try fixture()
        var result=try Wire.decoder().decode(ReconstructionResult.self,from:Data(contentsOf:root.appendingPathComponent("completion.json")))
        result.generatedTriangleCount=100_000
        try result.validate()
        result.generatedTriangleCount=200_001
        XCTAssertThrowsError(try result.validate())
        bundle.materials[0].roughness = .nan
        XCTAssertThrowsError(try bundle.validate(captureId:"analytic-room",revision:1,assets:assets))
        bundle.materials[0].roughness=0.5;bundle.materials[0].metallic=2
        XCTAssertThrowsError(try bundle.validate(captureId:"analytic-room",revision:1,assets:assets))
    }
}
