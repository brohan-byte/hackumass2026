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
}
struct RecognitionResult: Decodable {
    let detections: [RecognitionDetection]
    let views: Int
    let latencyMs: Int
}
struct RecognitionClient: Sendable {
    let server: String
    let token: String
    func call<T: Decodable>(_ path: String, body: [String: Any]? = nil) async throws -> T {
        let base = server.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: base + "/mobile/vision" + path) else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 90
        request.setValue("Bearer " + token.trimmingCharacters(in: .whitespacesAndNewlines), forHTTPHeaderField: "Authorization")
        if let body {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data,response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(response.statusCode) else {
            let message = (try? JSONDecoder().decode([String:String].self, from: data))?["error"] ?? "Vision HTTP \(response.statusCode)"
            throw NSError(domain:"GhostUI Vision", code:response.statusCode, userInfo:[NSLocalizedDescriptionKey:message])
        }
        return try JSONDecoder().decode(T.self,from:data)
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
