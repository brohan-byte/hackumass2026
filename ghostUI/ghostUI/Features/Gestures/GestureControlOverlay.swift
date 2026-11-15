#if os(iOS)
import SwiftUI

struct HandCursorOverlay: View {
    @ObservedObject var hand: HandGestureController
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                ForEach(Array(hand.landmarks.enumerated()),id: \.offset) { _,p in
                    Circle().fill(.cyan).frame(width:6,height:6)
                        .position(x:p.x*geometry.size.width,y:p.y*geometry.size.height)
                }
                if let p=hand.cursor {
                    Circle().stroke(hand.pinchActive ? .green : hand.hoveredTarget == nil ? .orange : .cyan,lineWidth:4)
                        .frame(width:36,height:36)
                        .position(x:p.x*geometry.size.width,y:p.y*geometry.size.height)
                }
            }
        }.allowsHitTesting(false)
    }
}
struct GestureControlOverlay: View {
    let deviceName: String
    let layoutTitle: String
    let groups: [String:String]
    let layoutNotice: String
    let controls: [DeviceControl]
    let values: [String:Double]
    @ObservedObject var hand: HandGestureController
    let deviceStatus: String
    let onBack: () -> Void
    let onClose: () -> Void
    let onTouch: () -> Void
    var body: some View {
        GeometryReader { geometry in
            let targets=GestureHUDLayout.targets(controlIDs:controls.map(\.id))
            ZStack {
                ForEach(targets,id: \.id) { target in
                    targetView(target)
                        .frame(width:target.rect.width*geometry.size.width,height:target.rect.height*geometry.size.height)
                        .background(hand.hoveredTarget==target.id ? Color.teal.opacity(0.85) : Color.black.opacity(0.65))
                        .clipShape(RoundedRectangle(cornerRadius:14))
                        .overlay(RoundedRectangle(cornerRadius:14).stroke(.mint.opacity(0.7),lineWidth:2))
                        .position(x:target.rect.midX*geometry.size.width,y:target.rect.midY*geometry.size.height)
                }
                Text(layoutTitle)
                    .font(.headline).padding(6).background(.regularMaterial)
                    .position(x:geometry.size.width*0.5,y:geometry.size.height*0.15)
                VStack(spacing:6) {
                    Text(hand.message).font(.callout).multilineTextAlignment(.center)
                    Text(layoutNotice).font(.caption2).lineLimit(2)
                    Text(deviceStatus).font(.caption).foregroundStyle(.secondary)
                    Button("Use touch sliders",action:onTouch).font(.caption)
                }.padding(8).frame(width:geometry.size.width*0.94)
                    .background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius:12))
                    .position(x:geometry.size.width*0.5,y:geometry.size.height*0.90)
                HandCursorOverlay(hand:hand)
            }.foregroundStyle(.white)
        }
        .onAppear { hand.configureSliders(controls,values:values) }
        .onChange(of:values) { _,newValues in hand.configureSliders(controls,values:newValues) }
    }
    @ViewBuilder private func targetView(_ target: GestureTarget) -> some View {
        if target.id=="back" { Button("Back",action:onBack) }
        else if target.id=="close" { Button("Close AR",action:onClose) }
        else if target.id.hasPrefix("control:") {
            let id=String(target.id.dropFirst(8))
            if let c=controls.first(where:{$0.id==id}) {
                let dragging=hand.selectedControlID==id && hand.previewValue != nil
                let value=dragging ? (hand.previewValue ?? c.min) : (values[id] ?? c.min)
                let fraction=GestureHUDLayout.fraction(value:value,min:c.min,max:c.max)
                GeometryReader { card in
                    let top=(GestureHUDLayout.railTop-target.rect.minY)/target.rect.height*card.size.height
                    let length=GestureHUDLayout.railLength/target.rect.height*card.size.height
                    let y=top+(1-fraction)*length
                    let ready=hand.hoveredTarget==target.id || dragging
                    ZStack {
                        VStack(spacing:2) {
                            Text(groups[id] ?? "Controls").font(.caption2).foregroundStyle(.secondary)
                            Text(c.label).font(.subheadline.bold())
                        }.lineLimit(1).minimumScaleFactor(0.65)
                            .position(x:card.size.width/2,y:card.size.height*0.08)
                        Text("\(Int(value))").font(.title2.monospacedDigit())
                            .foregroundStyle(dragging ? .green : .white)
                            .position(x:card.size.width/2,y:card.size.height*0.17)
                        Capsule().fill(.white.opacity(0.3)).frame(width:8,height:length)
                            .position(x:card.size.width/2,y:top+length/2)
                        Capsule().fill(.mint).frame(width:8,height:length*fraction)
                            .position(x:card.size.width/2,y:y+length*fraction/2)
                        Circle().fill(ready ? .mint.opacity(0.25) : .clear)
                            .frame(width:58,height:58)
                            .overlay(Circle().stroke(ready ? Color.mint : Color.clear,lineWidth:2))
                            .position(x:card.size.width/2,y:y)
                        Circle().fill(dragging ? .green : .mint).frame(width:34,height:34)
                            .overlay(Circle().stroke(.white,lineWidth:2))
                            .position(x:card.size.width/2,y:y)
                        Text("\(Int(c.max))").font(.caption2)
                            .position(x:card.size.width/2,y:top-16)
                        Text("\(Int(c.min))").font(.caption2)
                            .position(x:card.size.width/2,y:top+length+18)
                        Text(dragging ? "Release to apply" : ready ? "Pinch to grab" : "Pinch · drag ↕")
                            .font(.caption2).multilineTextAlignment(.center)
                            .frame(width:card.size.width-6)
                            .position(x:card.size.width/2,y:card.size.height*0.94)
                    }
                }.allowsHitTesting(false)
            }
        }
    }
}
#endif
