import DincrCore
import UIKit

/// Every text field of the app can hide its keyboard: the decimal and number pads have no return
/// key, and a keyboard left open covers the form's buttons. It sits on UIKit's "editing began"
/// notifications so that no field, sheet or future form has to remember it. A field that already
/// has its own accessory view keeps it.
@MainActor
final class KeyboardHideBar: NSObject {
    static let shared = KeyboardHideBar()

    func install() {
        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(editingBegan), name: UITextField.textDidBeginEditingNotification, object: nil)
        center.addObserver(self, selector: #selector(editingBegan), name: UITextView.textDidBeginEditingNotification, object: nil)
    }

    @objc private func editingBegan(_ notification: Notification) {
        if let field = notification.object as? UITextField, field.inputAccessoryView == nil {
            field.inputAccessoryView = bar()
            field.reloadInputViews()
        } else if let view = notification.object as? UITextView, view.isEditable, view.inputAccessoryView == nil {
            view.inputAccessoryView = bar()
            view.reloadInputViews()
        }
    }

    private func bar() -> UIToolbar {
        let toolbar = UIToolbar(frame: CGRect(x: 0, y: 0, width: 320, height: 44))
        let hide = UIBarButtonItem(image: UIImage(systemName: "keyboard.chevron.compact.down"), primaryAction: UIAction { _ in
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
        })
        hide.accessibilityLabel = tx("Ocultar teclado", "Hide keyboard")
        hide.accessibilityIdentifier = "keyboard.hide"
        toolbar.items = [.flexibleSpace(), hide]
        toolbar.sizeToFit()
        return toolbar
    }
}
