#if os(iOS)
import Foundation
import CoreGraphics

struct RecognitionStatus: Decodable {
    let views: Int
    let modelAvailable: Bool
}
struct RecognitionDetection: Decodable {
    let box: [Double]
    let score: Double
    let polygon: [[Double]]?
    let deviceId: String?
    let name: String?
}
struct RecognitionResult: Decodable {
    let detections: [RecognitionDetection]
    let views: Int
    let latencyMs: Int
}
struct RecognitionClient: Sendable {
    let server: String
    let token: String
    var deviceID: String? = nil
    var isScene = false
    func call<T: Decodable>(_ path: String, body: [String: Any]? = nil) async throws -> T {
        let api = GhostAPIClient(server:server,token:token,deviceID:isScene ? nil : deviceID)
        return try await api.request((isScene ? "/mobile/scene/vision" : "/mobile/vision")+path,body:body,timeout:90)
    }

    func status() async throws -> RecognitionStatus { try await call("") }
    func enroll(_ image: Data, box: CGRect) async throws -> RecognitionStatus {
        let coordinates: [Double] = [
            Double(box.minX), Double(box.minY),
            Double(box.width), Double(box.height)
        ]
        let payload: [String: Any] = [
            "image": image.base64EncodedString(),
            "box": coordinates
        ]
        return try await call("/enroll", body: payload)
    }
    func clear() async throws -> RecognitionStatus { try await call("/clear",body:[:]) }
    func detect(_ image: Data) async throws -> RecognitionResult {
        try await call("/detect",body:["image":image.base64EncodedString()])
    }
}
#endif
