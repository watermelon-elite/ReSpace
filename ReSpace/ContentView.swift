import RoomPlan
import SwiftUI
import UIKit

struct ContentView: View {
    @State private var store: WorkspaceStore?
    @State private var startupError: String?
    @State private var recoveryMonitor: NetworkRecoveryMonitor?

    var body: some View {
        Group {
            if !supportedHardware {
                CompatibilityView()
            } else if let store {
                if store.localCaptureEnabled { LocalRoomsView(store: store) }
                else { MyRoomsView(store: store) }
            } else if let startupError {
                ContentUnavailableView("Couldn’t open ReSpace", systemImage: "externaldrive.badge.exclamationmark",
                                       description: Text(startupError))
            } else { ProgressView("Opening your rooms…") }
        }
        .tint(ReSpaceTheme.olive)
        .foregroundStyle(ReSpaceTheme.ink)
        .task {
            guard supportedHardware, store == nil else { return }
            do {
                let workspace = WorkspaceStore(configuration: try AppConfiguration.load(), deviceId: try DeviceIdentity.load())
                store = workspace
                if !workspace.localCaptureEnabled {
                    recoveryMonitor = NetworkRecoveryMonitor { [weak workspace] in await workspace?.bootstrap() }
                }
            }
            catch { startupError = error.localizedDescription }
        }
    }
    private var supportedHardware: Bool {
        UIDevice.current.model == "iPhone" && UIDevice.current.userInterfaceIdiom == .phone && RoomCaptureSession.isSupported
    }
}
