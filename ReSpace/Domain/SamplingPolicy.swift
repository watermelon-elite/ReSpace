import Foundation

struct SamplingObservation: Sendable {
    var time: Double
    var position: SIMD3<Float>
    var forward: SIMD3<Float>
    var trackingNormal: Bool
}

/// Pure admission policy. Buffer ownership and encoding capacity belong to Capture.
struct SamplingPolicy: Sendable {
    static let reconstructionMaximumFrames = 900
    static let reconstructionMinimumSeconds = 60
    static let reconstructionMaximumBytes = 2 * 1024 * 1024 * 1024
    var maximumFrames = 40
    var minimumInterval = 1.5
    var minimumDistance: Float = 0.5
    var minimumAngle: Float = .pi / 9
    private(set) var acceptedCount = 0
    private var lastObserved: SamplingObservation?
    private var lastAccepted: SamplingObservation?

    mutating func consider(_ sample: SamplingObservation, encoderAvailable: Bool) -> Bool {
        defer { lastObserved = sample }
        guard sample.trackingNormal, encoderAvailable, acceptedCount < maximumFrames else { return false }
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
            // A hard rate bound prevents bursts from small pose oscillations.
            guard sample.time - previous.time >= 0.3,
                  sample.time - previous.time >= minimumInterval || distance >= minimumDistance || angle >= minimumAngle else { return false }
        }
        acceptedCount += 1
        lastAccepted = sample
        return true
    }

    static var reconstruction: Self {
        Self(maximumFrames: reconstructionMaximumFrames, minimumInterval: 0.5,
             minimumDistance: 0.10, minimumAngle: .pi / 22.5)
    }
}
