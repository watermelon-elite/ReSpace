/// RoomPlan may add reconstruction features to the shared AR session. Mesh capture
/// requires the mesh flag to remain enabled, irrespective of additional options.
enum ScanMeshConfiguration {
    static func isEnabled<Features: OptionSet>(_ active: Features?, mesh: Features) -> Bool {
        active?.isSuperset(of: mesh) == true
    }
}
