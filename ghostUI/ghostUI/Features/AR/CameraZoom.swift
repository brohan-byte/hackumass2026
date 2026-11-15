#if os(iOS)
import SwiftUI

/// Digital zoom for the AR camera screens.
///
/// ARKit always runs the camera at 1x, so zoom scales the camera view *and*
/// the overlays drawn on it (boxes, contours, hand cursor) together, about the
/// centre. Every overlay keeps using the camera's unscaled coordinates, so
/// recognition, box drawing, touches and hand selection stay aligned with what
/// the user sees. Zoom applies only while the camera itself is on screen.
enum CameraZoom {
    static let presets: [CGFloat] = [1, 2, 3]
    static let range: ClosedRange<CGFloat> = 1...5
    static func clamp(_ value: CGFloat) -> CGFloat {
        min(max(value, range.lowerBound), range.upperBound)
    }
    static func label(_ value: CGFloat) -> String {
        let rounded = (value * 10).rounded() / 10
        return rounded == rounded.rounded()
            ? "\(Int(rounded))×" : String(format: "%.1f×", Double(rounded))
    }
}

private struct CameraZoomModifier: ViewModifier {
    @Binding var zoom: CGFloat
    let enabled: Bool
    @State private var pinchStart: CGFloat?

    func body(content: Content) -> some View {
        content
            .scaleEffect(enabled ? zoom : 1, anchor: .center)
            .clipped()
            .simultaneousGesture(
                MagnifyGesture()
                    .onChanged { value in
                        let start = pinchStart ?? zoom
                        pinchStart = start
                        zoom = CameraZoom.clamp(start * value.magnification)
                    }
                    .onEnded { _ in pinchStart = nil },
                including: enabled ? .all : .subviews)
    }
}

extension View {
    /// Pinch-to-zoom plus scaling for the camera and everything drawn on it.
    func cameraZoom(_ zoom: Binding<CGFloat>, enabled: Bool) -> some View {
        modifier(CameraZoomModifier(zoom: zoom, enabled: enabled))
    }
}

/// 1× / 2× / 3× buttons, like the system Camera app. The active button shows
/// the exact pinch value (for example 2.4×).
struct CameraZoomPicker: View {
    @Binding var zoom: CGFloat

    private var activePreset: CGFloat {
        CameraZoom.presets.last(where: { zoom >= $0 - 0.05 }) ?? 1
    }

    var body: some View {
        HStack(spacing: 6) {
            ForEach(CameraZoom.presets, id: \.self) { preset in
                let active = preset == activePreset
                Button {
                    withAnimation(.easeOut(duration: 0.2)) { zoom = preset }
                } label: {
                    Text(active ? CameraZoom.label(zoom) : CameraZoom.label(preset))
                        .font(.caption.bold().monospacedDigit())
                        .foregroundStyle(active ? .yellow : .white)
                        .frame(minWidth: 36, minHeight: 36)
                        .background(Circle().fill(.black.opacity(active ? 0.55 : 0.3)))
                }
                .accessibilityLabel("Zoom \(CameraZoom.label(preset))")
                .accessibilityAddTraits(active ? .isSelected : [])
            }
        }
        .padding(4)
        .background(.ultraThinMaterial, in: Capsule())
    }
}
#endif
