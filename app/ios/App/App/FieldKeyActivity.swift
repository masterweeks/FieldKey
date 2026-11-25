import Foundation
#if canImport(ActivityKit)
import ActivityKit

/// FieldKey's Live Activity: progress shown on the Lock Screen, in the Dynamic Island, and on the
/// CarPlay dashboard (iOS 26). Compiled into both the app (which starts and updates it, see
/// FieldKeyLiveActivity.swift) and the FieldKeyWidgets extension (which draws it).
/// kind "texting": headline "Texting · 7 of 23 sent", detail "Next: SAP 12345".
/// kind "route" (today's scheduled sites): headline "Next: SAP 12345 · 10:30", detail "Gate code 2211 · 412 Oak Ridge Rd".
@available(iOS 16.2, *)
public struct FieldKeyActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        public var headline: String
        public var detail: String
        public var done: Int
        public var total: Int

        public init(headline: String, detail: String, done: Int, total: Int) {
            self.headline = headline
            self.detail = detail
            self.done = done
            self.total = total
        }
    }

    /// What the activity is about, e.g. "texting".
    public var kind: String

    public init(kind: String) {
        self.kind = kind
    }
}
#endif
