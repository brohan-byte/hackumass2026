#if os(iOS)
import SwiftUI
import UIKit

struct ObjectSelectionOverlay: View {
    let box: CGRect?
    let selecting: Bool
    let deviceName: String
    let onRegister: (CGRect) -> Void
    let onSelect: () -> Void
    var onInvalid: () -> Void = {}

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .topLeading) {
                if selecting {
                    SelectionDrawingView(onComplete: onRegister, onInvalid: onInvalid)
                    if let box {
                        outline(screenRect(box, geometry.size), color: .yellow).allowsHitTesting(false)
                    }
                } else if let box {
                    let rect = screenRect(box, geometry.size)
                    outline(rect, color: .mint).allowsHitTesting(false)
                    Button(action: onSelect) { Color.clear.contentShape(Rectangle()) }
                        .buttonStyle(.plain)
                        .frame(width: max(44, rect.width + 40), height: max(44, rect.height + 40))
                        .position(x: rect.midX, y: rect.midY)
                        .accessibilityLabel("Open controls for " + deviceName)
                    Text(deviceName + " · Tap for controls")
                        .font(.caption.bold()).padding(6).background(.ultraThinMaterial)
                        .position(x: rect.midX, y: max(16, rect.minY - 18)).allowsHitTesting(false)
                }
            }
        }
    }
    private func screenRect(_ box: CGRect, _ size: CGSize) -> CGRect {
        CGRect(x:box.minX*size.width,y:box.minY*size.height,width:box.width*size.width,height:box.height*size.height)
    }
    private func outline(_ rect: CGRect, color: Color) -> some View {
        RoundedRectangle(cornerRadius: 12).stroke(color, lineWidth: 3)
            .shadow(color: color.opacity(0.8), radius: 9)
            .frame(width: rect.width, height: rect.height).position(x: rect.midX, y: rect.midY)
    }
}

/// Native gesture surface, independent of the AR renderer's gesture handling.
struct SelectionDrawingView: UIViewRepresentable {
    let onComplete: (CGRect) -> Void
    let onInvalid: () -> Void
    func makeUIView(context: Context) -> DrawingCanvas {
        let view = DrawingCanvas(); view.onComplete = onComplete; view.onInvalid = onInvalid
        return view
    }
    func updateUIView(_ view: DrawingCanvas, context: Context) {
        view.onComplete = onComplete; view.onInvalid = onInvalid
    }
}
final class DrawingCanvas: UIView {
    var onComplete: ((CGRect) -> Void)?
    var onInvalid: (() -> Void)?
    private var start: CGPoint?
    private let shape = CAShapeLayer()
    override init(frame: CGRect) {
        super.init(frame:frame)
        backgroundColor = .clear; isOpaque = false; isUserInteractionEnabled = true
        shape.fillColor = UIColor.yellow.withAlphaComponent(0.08).cgColor
        shape.strokeColor = UIColor.yellow.cgColor; shape.lineWidth = 3
        layer.addSublayer(shape)
        let pan = UIPanGestureRecognizer(target:self,action:#selector(drag(_:)))
        pan.maximumNumberOfTouches = 1
        addGestureRecognizer(pan)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }
    override func layoutSubviews() { super.layoutSubviews(); shape.frame = bounds }
    @objc private func drag(_ gesture: UIPanGestureRecognizer) {
        let location = gesture.location(in:self)
        if gesture.state == .began {
            let delta = gesture.translation(in:self)
            start = CGPoint(x:location.x-delta.x,y:location.y-delta.y)
        }
        guard let start else { return }
        let rect = CGRect(x:min(start.x,location.x),y:min(start.y,location.y),
                          width:abs(start.x-location.x),height:abs(start.y-location.y)).intersection(bounds)
        if !rect.isNull { shape.path = UIBezierPath(roundedRect:rect,cornerRadius:10).cgPath }
        if gesture.state == .ended {
            defer { self.start = nil; shape.path = nil }
            guard !rect.isNull,rect.width>=44,rect.height>=44,bounds.width>0,bounds.height>0 else {
                onInvalid?(); return
            }
            let box = CGRect(x:rect.minX/bounds.width,y:rect.minY/bounds.height,
                             width:rect.width/bounds.width,height:rect.height/bounds.height)
            print("GhostUI enrollment: box drawn \(box)")
            onComplete?(box)
        } else if gesture.state == .cancelled || gesture.state == .failed {
            self.start = nil; shape.path = nil
        }
    }
}
#endif
