import Foundation

struct SamplingObservation: Sendable {
    var time: Double
    var position: SIMD3<Float>
    var forward: SIMD3<Float>
    var trackingNormal: Bool
}

/// Pure admission policy. Buffer ownership and encoding capacity belong to Capture.
struct SamplingPolicy: Sendable {
    private(set) var acceptedCount = 0
    private var lastObserved: SamplingObservation?
    private var lastAccepted: SamplingObservation?

    mutating func consider(_ sample: SamplingObservation, encoderAvailable: Bool) -> Bool {
        defer { lastObserved = sample }
        guard sample.trackingNormal, encoderAvailable, acceptedCount < 40 else { return false }
        if let previous = lastObserved {
            let dt = sample.time - previous.time
            guard dt > 0 else { return false }
            let delta = sample.position - previous.position
            let distance = sqrt(delta.x * delta.x + delta.y * delta.y + delta.z * delta.z)
            guard Double(distance) / dt <= 0.3 else { return false }
        }
        if let previous = lastAccepted {
            let delta = sample.position - previous.position
            let distance = sqrt(delta.x * delta.x + delta.y * delta.y + delta.z * delta.z)
            let dot = sample.forward.x * previous.forward.x + sample.forward.y * previous.forward.y + sample.forward.z * previous.forward.z
            let angle = acos(max(-1, min(1, dot)))
            guard sample.time - previous.time >= 1.5 || distance >= 0.5 || angle >= .pi / 9 else { return false }
        }
        acceptedCount += 1
        lastAccepted = sample
        return true
    }
}
