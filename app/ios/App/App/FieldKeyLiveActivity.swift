import Foundation
import Capacitor
#if canImport(ActivityKit)
import ActivityKit
#endif

/// Starts, updates and ends FieldKey's Live Activity (FieldKeyActivity.swift; drawn by the
/// FieldKeyWidgets extension). Needs iOS 16.2 or later and Live Activities allowed for FieldKey;
/// otherwise every call quietly does nothing.
/// Each kind ("texting", "route") is its own activity; starting, updating or ending one leaves the others.
/// JS: Capacitor.nativePromise("FieldKeyLiveActivity", "start" | "update", {kind, headline, detail, done, total})
///     Capacitor.nativePromise("FieldKeyLiveActivity", "end", {kind})
@objc(FieldKeyLiveActivityPlugin)
public class FieldKeyLiveActivityPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FieldKeyLiveActivityPlugin"
    public let jsName = "FieldKeyLiveActivity"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "start", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "update", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "end", returnType: CAPPluginReturnPromise)
    ]

    @objc func start(_ call: CAPPluginCall) {
        #if canImport(ActivityKit)
        if #available(iOS 16.2, *) {
            let kind = call.getString("kind") ?? "texting"
            let state = Self.state(call)
            Task {
                await LiveActivities.end(kind: kind)
                let started = LiveActivities.start(kind: kind, state: state)
                call.resolve(["started": started])
            }
            return
        }
        #endif
        call.resolve(["started": false])
    }

    @objc func update(_ call: CAPPluginCall) {
        #if canImport(ActivityKit)
        if #available(iOS 16.2, *) {
            let kind = call.getString("kind") ?? "texting"
            let state = Self.state(call)
            Task { await LiveActivities.update(kind: kind, state); call.resolve() }
            return
        }
        #endif
        call.resolve()
    }

    @objc func end(_ call: CAPPluginCall) {
        #if canImport(ActivityKit)
        if #available(iOS 16.2, *) {
            let kind = call.getString("kind") ?? "texting"
            Task { await LiveActivities.end(kind: kind); call.resolve() }
            return
        }
        #endif
        call.resolve()
    }

    #if canImport(ActivityKit)
    @available(iOS 16.2, *)
    private static func state(_ call: CAPPluginCall) -> FieldKeyActivityAttributes.ContentState {
        FieldKeyActivityAttributes.ContentState(
            headline: call.getString("headline") ?? "",
            detail: call.getString("detail") ?? "",
            done: call.getInt("done") ?? 0,
            total: call.getInt("total") ?? 0)
    }
    #endif
}

#if canImport(ActivityKit)
@available(iOS 16.2, *)
enum LiveActivities {
    static func start(kind: String, state: FieldKeyActivityAttributes.ContentState) -> Bool {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return false }
        do {
            _ = try Activity.request(attributes: FieldKeyActivityAttributes(kind: kind),
                                     content: ActivityContent(state: state, staleDate: nil))
            return true
        } catch {
            return false
        }
    }

    static func update(kind: String, _ state: FieldKeyActivityAttributes.ContentState) async {
        for activity in Activity<FieldKeyActivityAttributes>.activities where activity.attributes.kind == kind {
            await activity.update(ActivityContent(state: state, staleDate: nil))
        }
    }

    static func end(kind: String) async {
        for activity in Activity<FieldKeyActivityAttributes>.activities where activity.attributes.kind == kind {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }
}
#endif
