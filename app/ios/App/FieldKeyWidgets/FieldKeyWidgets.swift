import WidgetKit
import SwiftUI
import ActivityKit

/// FieldKey's widget extension. It draws the Live Activity the app starts (FieldKeyActivity.swift,
/// FieldKeyLiveActivity.swift): Lock Screen, Dynamic Island, and the small "supplemental" family used
/// by Apple Watch's Smart Stack and, on iOS 26, the CarPlay dashboard.
@main
struct FieldKeyWidgetsBundle: WidgetBundle {
    var body: some Widget {
        FieldKeyLiveActivityWidget()
    }
}

private let amber = Color(red: 1.0, green: 0.69, blue: 0.0)
private let ink = Color(red: 0.055, green: 0.067, blue: 0.086)

struct FieldKeyLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: FieldKeyActivityAttributes.self) { context in
            ActivityView(state: context.state, kind: context.attributes.kind)
                .activityBackgroundTint(ink)
                .activitySystemActionForegroundColor(amber)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: icon(context.attributes.kind)).foregroundStyle(amber).font(.title2)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(context.state.done)/\(context.state.total)").monospacedDigit().font(.title3.bold())
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(context.state.headline).font(.headline).lineLimit(1)
                        Text(context.state.detail).font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
                        Progress(done: context.state.done, total: context.state.total)
                    }
                }
            } compactLeading: {
                Image(systemName: icon(context.attributes.kind)).foregroundStyle(amber)
            } compactTrailing: {
                Text("\(context.state.done)/\(context.state.total)").monospacedDigit()
            } minimal: {
                Text("\(context.state.done)").monospacedDigit().foregroundStyle(amber)
            }
            .keylineTint(amber)
        }
        .supplementalActivityFamilies([.small])
    }
}

private func icon(_ kind: String) -> String {
    kind == "texting" ? "message.fill" : "mappin.circle.fill"
}

struct ActivityView: View {
    let state: FieldKeyActivityAttributes.ContentState
    let kind: String
    @Environment(\.activityFamily) private var family

    var body: some View {
        if family == .small {
            // Smart Stack and CarPlay: small and glanceable.
            VStack(alignment: .leading, spacing: 2) {
                Label(state.headline, systemImage: icon(kind)).font(.caption.bold()).lineLimit(1)
                Text(state.detail).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                Progress(done: state.done, total: state.total)
            }
            .foregroundStyle(.white)
            .padding(8)
        } else {
            HStack(alignment: .center, spacing: 14) {
                Image(systemName: icon(kind)).font(.title).foregroundStyle(amber)
                VStack(alignment: .leading, spacing: 4) {
                    Text(state.headline).font(.headline).foregroundStyle(.white).lineLimit(1)
                    Text(state.detail).font(.subheadline).foregroundStyle(.white.opacity(0.75)).lineLimit(1)
                    Progress(done: state.done, total: state.total)
                }
            }
            .padding(16)
        }
    }
}

struct Progress: View {
    let done: Int
    let total: Int
    var body: some View {
        ProgressView(value: Double(min(done, max(total, 1))), total: Double(max(total, 1)))
            .tint(amber)
    }
}
