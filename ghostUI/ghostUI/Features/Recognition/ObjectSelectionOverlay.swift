#if os(iOS)
import SwiftUI
import UIKit

struct ObjectSelectionOverlay: View {
    let box: CGRect?
    var contour: [CGPoint] = []
    let selecting: Bool
    let deviceName: String
    var onBeginRegistration: () -> Void = {}
    let onRegister: (CGRect) -> Void
    let onSelect: () -> Void
    var onInvalid: () -> Void = {}
    var onSelectionBegan: () -> Void = {}
    var onSelectionEnded: () -> Void = {}

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .topLeading) {
                if selecting {
                    SelectionDrawingView(onBegin:onBeginRegistration,onComplete: onRegister, onInvalid: onInvalid)
                    if let box {
                        outline(screenRect(box, geometry.size), color: .yellow).allowsHitTesting(false)
                    }
                } else if let box {
                    let rect = screenRect(box, geometry.size)
                    if contour.count >= 3 {
                        Path { path in
                            path.move(to:CGPoint(x:contour[0].x*geometry.size.width,y:contour[0].y*geometry.size.height))
                            for p in contour.dropFirst() { path.addLine(to:CGPoint(x:p.x*geometry.size.width,y:p.y*geometry.size.height)) }
                            path.closeSubpath()
                        }
                        .fill(Color.mint.opacity(0.10))
                        .overlay {
                            Path { path in
                                path.move(to:CGPoint(x:contour[0].x*geometry.size.width,y:contour[0].y*geometry.size.height))
                                for p in contour.dropFirst() { path.addLine(to:CGPoint(x:p.x*geometry.size.width,y:p.y*geometry.size.height)) }
                                path.closeSubpath()
                            }.stroke(.mint,lineWidth:3).shadow(color:.mint,radius:8)
                        }.allowsHitTesting(false)
                    } else { outline(rect,color:.mint).allowsHitTesting(false) }
                    ObjectHitSurface(label:"Open controls for " + deviceName,
                        onBegin:onSelectionBegan,onSelect:onSelect,onEnd:onSelectionEnded)
                        .frame(width: max(44, rect.width + 40), height: max(44, rect.height + 40))
                        .position(x: rect.midX, y: rect.midY)
                    Text(deviceName + " · Tap for controls")
                        .font(.caption.bold()).padding(6).background(.ultraThinMaterial)
                        .overlay {
                            ObjectHitSurface(label:"Open controls for " + deviceName,
                                onBegin:onSelectionBegan,onSelect:onSelect,onEnd:onSelectionEnded)
                        }
                        .position(x: rect.midX, y: max(16, rect.minY - 18))
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

/// Capture the device at touch-down, before moving camera geometry can remove
/// its hit area. UIKit preserves normal touch-up-inside/cancel behavior.
private struct ObjectHitSurface: UIViewRepresentable {
    let label: String
    let onBegin: () -> Void
    let onSelect: () -> Void
    let onEnd: () -> Void
    func makeUIView(context: Context) -> ObjectHitButton { ObjectHitButton(frame:.zero) }
    func updateUIView(_ view: ObjectHitButton,context: Context) {
        view.accessibilityLabel=label
        view.onBegin=onBegin;view.onSelect=onSelect;view.onEnd=onEnd
    }
}
private final class ObjectHitButton: UIButton {
    var onBegin: (() -> Void)?
    var onSelect: (() -> Void)?
    var onEnd: (() -> Void)?
    override init(frame: CGRect) {
        super.init(frame:frame)
        backgroundColor = .clear
        addTarget(self,action:#selector(began),for:.touchDown)
        addTarget(self,action:#selector(selected),for:.touchUpInside)
        addTarget(self,action:#selector(cancelled),for:[.touchUpOutside,.touchCancel])
    }
    required init?(coder:NSCoder) { fatalError("init(coder:) is not used") }
    @objc private func began() { onBegin?() }
    @objc private func selected() { onSelect?();onEnd?() }
    @objc private func cancelled() { onEnd?() }
}

/// Native gesture surface, independent of the AR renderer's gesture handling.
struct SelectionDrawingView: UIViewRepresentable {
    let onBegin: () -> Void
    let onComplete: (CGRect) -> Void
    let onInvalid: () -> Void
    func makeUIView(context: Context) -> DrawingCanvas {
        let view = DrawingCanvas(); view.onBegin = onBegin; view.onComplete = onComplete; view.onInvalid = onInvalid
        return view
    }
    func updateUIView(_ view: DrawingCanvas, context: Context) {
        view.onBegin = onBegin; view.onComplete = onComplete; view.onInvalid = onInvalid
    }
}
final class DrawingCanvas: UIView {
    var onBegin: (() -> Void)?
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
            onBegin?()
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
