/// A screen the system can ask the app to open: an App Shortcut (the Shortcuts app, Siri, Back Tap
/// on the back of the iPhone) or, on Android, a launcher shortcut. It only opens the screen; the
/// user still saves. The signed-in, unlocked shell is the only place that acts on it
/// (Android: `QuickAction`).
public enum QuickAction: String, Sendable, CaseIterable {
    /// The movement editor, ready for a new expense.
    case newExpense = "new_expense"

    /// The app's pending-route value for this action.
    public var route: String { rawValue }

    public init?(route: String) { self.init(rawValue: route) }

    /// `-DincrQuickAction <route>` (UI tests and screenshots, as `-DincrTab`).
    public static func fromLaunchArguments(_ arguments: [String]) -> QuickAction? {
        guard let index = arguments.firstIndex(of: "-DincrQuickAction"), arguments.indices.contains(index + 1) else { return nil }
        return QuickAction(route: arguments[index + 1])
    }
}
