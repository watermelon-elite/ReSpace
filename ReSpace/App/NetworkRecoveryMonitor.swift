import Network

/// Retry already journaled work when connectivity returns; never invent a new operation.
@MainActor final class NetworkRecoveryMonitor {
    private let monitor = NWPathMonitor()
    private var previouslyConnected: Bool?
    private let reconnect: @MainActor () async -> Void

    init(reconnect: @escaping @MainActor () async -> Void) {
        self.reconnect = reconnect
        monitor.pathUpdateHandler = { [weak self] path in
            guard let observer = self else { return }
            let connected = path.status == .satisfied
            Task { @MainActor in await observer.changed(connected) }
        }
        monitor.start(queue: DispatchQueue(label: "ReSpace.recovery-connectivity"))
    }
    private func changed(_ connected: Bool) async {
        let old = previouslyConnected
        previouslyConnected = connected
        if old == false && connected { await reconnect() }
    }
    deinit { monitor.cancel() }
}
