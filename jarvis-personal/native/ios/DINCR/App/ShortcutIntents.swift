import AppIntents
import DincrCore
import Foundation

// Atajos de iPhone (Perfil → Atajos de iPhone; VIP and the Owner). Two App Intents that run in the
// background from a Shortcuts automation and send what they receive to Movimientos → Por revisar, with
// the limited token in the Keychain (never the app session). Nothing is recorded until the user
// reviews it. They never log the token, the amount, the merchant, the card or the message.

/// Moneda: the currency of the Wallet card, used when the amount carries no ₡ / $ / code.
enum ShortcutCurrencyOption: String, AppEnum {
    case crc = "CRC"
    case usd = "USD"

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Moneda"
    static let caseDisplayRepresentations: [ShortcutCurrencyOption: DisplayRepresentation] = [
        .crc: "Colones (CRC)",
        .usd: "Dólares (USD)",
    ]

    var currency: ShortcutCurrency { self == .usd ? .usd : .crc }
}

/// The error an intent shows: a plain sentence, no internals.
struct ShortcutIntentError: Error, CustomLocalizedStringResourceConvertible {
    let message: String
    var localizedStringResource: LocalizedStringResource { LocalizedStringResource(stringLiteral: message) }
}

/// Builds the capture client for a background run. The intent runs without launch arguments, so only a
/// configured (live) build can send; fixtures and an unconfigured build refuse plainly.
enum ShortcutIntentRuntime {
    static func client() throws -> ShortcutCaptureClient {
        guard case let .live(apiURL, _, _) = AppEnvironment.current().mode else {
            throw ShortcutIntentError(message: tx("DINCR no está lista en este iPhone. Abrí la app e intentá de nuevo.",
                                                  "DINCR isn’t ready on this iPhone. Open the app and try again."))
        }
        return ShortcutCaptureClient(store: KeychainShortcutTokenStore(), sender: ShortcutSender(baseURL: apiURL))
    }
}

/// For the *Transacción* automation (Apple Pay / Wallet).
struct RegisterApplePayPurchaseIntent: AppIntent {
    static let title: LocalizedStringResource = "Registrar compra en DINCR"
    static let description = IntentDescription(
        "Envía una compra con Apple Pay a DINCR para que la revisés en Movimientos → Por revisar. Usala en la automatización Transacción.")
    static let openAppWhenRun = false

    @Parameter(title: "Monto", description: "El monto de la compra, con o sin símbolo de moneda.")
    var amount: String

    @Parameter(title: "Moneda", description: "La moneda de la tarjeta, si el monto no la indica.", default: .crc)
    var currency: ShortcutCurrencyOption

    @Parameter(title: "Comercio", description: "Dónde se hizo la compra.")
    var merchant: String

    @Parameter(title: "Tarjeta", description: "Opcional: la tarjeta de Wallet.")
    var card: String?

    static var parameterSummary: some ParameterSummary {
        Summary("Registrar compra de \(\.$amount) en \(\.$merchant)") {
            \.$currency
            \.$card
        }
    }

    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let client = try ShortcutIntentRuntime.client()
        do {
            let result = try await client.registerPurchase(amount: amount, currency: currency.currency, merchant: merchant, card: card)
            let message = result.purchaseMessage()
            return .result(value: message, dialog: IntentDialog(stringLiteral: message))
        } catch {
            throw ShortcutIntentError(message: error.message(.purchase))
        }
    }
}

/// For the *Mensaje* automation (a bank's SMS).
struct SendBankMessageIntent: AppIntent {
    static let title: LocalizedStringResource = "Enviar aviso bancario a DINCR"
    static let description = IntentDescription(
        "Envía el texto de un SMS de tu banco a DINCR para que lo revisés en Movimientos → Por revisar. Usala en la automatización Mensaje.")
    static let openAppWhenRun = false

    @Parameter(title: "Texto del mensaje", description: "El texto del SMS del banco (la variable Mensaje).")
    var text: String

    static var parameterSummary: some ParameterSummary {
        Summary("Enviar \(\.$text) a DINCR")
    }

    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let client = try ShortcutIntentRuntime.client()
        do {
            let result = try await client.sendBankMessage(text)
            let message = result.bankMessageMessage()
            return .result(value: message, dialog: IntentDialog(stringLiteral: message))
        } catch {
            throw ShortcutIntentError(message: error.message(.bankMessage))
        }
    }
}
