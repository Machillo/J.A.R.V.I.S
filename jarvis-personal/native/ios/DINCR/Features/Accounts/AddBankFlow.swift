import DincrCore
import DincrDesign
import SwiftUI

/// The Owner adds a bank (Cuentas → Agregar cuenta): pick it, confirm the accounts DINCR found in the
/// connected mail or add one by hand, and see what was added. It only uses Cuentas' own commands
/// (ownership answers, a declared own account), one per tap. No balance: a detected account's is unknown.
struct AddBankFlow: View {
    private enum Step: Equatable {
        case pick
        case review(BankBrand)
        case done([FinancialIdentity.Account])
    }

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var step: Step = .pick
    @State private var query = ""
    @State private var found: [FinancialIdentity.Account]?
    @State private var chosen: Set<Int> = []
    @State private var error: String?
    @State private var saving = false
    @State private var manual: BankBrand??

    var body: some View {
        NavigationStack {
            Group {
                switch step {
                case .pick: pick
                case .review(let brand): review(brand)
                case .done(let accounts): done(accounts)
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if case .review = step {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { step = .pick } label: { Image(systemName: "chevron.left") }
                            .accessibilityLabel(tx("Volver", "Back"))
                    }
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(tx("Cerrar", "Close"))
                        .accessibilityIdentifier("addBank.close")
                }
            }
            .dincrScreenBackground()
        }
        .interactiveDismissDisabled(saving)
        .sheet(item: manualBinding) { choice in
            DeclareOwnAccountForm(institutionCode: Self.declaredCode(choice.brand), institutionLabel: Self.declaredName(choice.brand)) { _ in
                Task { await showDeclared(choice.brand) }
            }
        }
    }

    private var title: String {
        switch step {
        case .pick: tx("Agregar cuenta", "Add account")
        case .review(let brand): brand.name
        case .done: tx("Listo", "Done")
        }
    }

    // MARK: Pick

    private var banks: [BankBrand] {
        let all = BankBrand.onboardingChoices.map { BankBrand.describe($0.id) }
        let text = query.trimmingCharacters(in: .whitespaces)
        return text.isEmpty ? all : all.filter { SearchText.matches(text, in: [$0.name, $0.short]) }
    }

    private var pick: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                TextField(tx("Buscá tu banco", "Search for your bank"), text: $query)
                    .padding(.horizontal, DincrSpacing.s4)
                    .frame(minHeight: 48)
                    .background(OwnerColor.surface, in: Capsule())
                    .accessibilityIdentifier("addBank.search")
                LazyVGrid(columns: [GridItem(.flexible(), spacing: DincrSpacing.s3), GridItem(.flexible(), spacing: DincrSpacing.s3)], spacing: DincrSpacing.s3) {
                    ForEach(banks, id: \.id) { brand in
                        Button { open(brand) } label: {
                            VStack(spacing: DincrSpacing.s2) {
                                BankLogo(brand: brand, size: 48)
                                Text(brand.name).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(.dincrText)
                                    .multilineTextAlignment(.center).lineLimit(2)
                            }
                            .frame(maxWidth: .infinity, minHeight: 112)
                            .background(OwnerColor.surface, in: RoundedRectangle(cornerRadius: OwnerRadius.card, style: .continuous))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("addBank.bank.\(brand.id)")
                    }
                }
                if banks.isEmpty {
                    Text(tx("Ese banco no está en la lista. Podés agregarlo a mano.", "That bank isn’t on the list. You can add it by hand."))
                        .font(DincrFont.bodySmall).foregroundStyle(.dincrText2)
                }
                Button { manual = .some(nil) } label: { Text(tx("Agregar otra institución a mano", "Add another institution by hand")) }
                    .buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("addBank.manual")
            }
            .padding(DincrSpacing.s4)
        }
    }

    private func open(_ brand: BankBrand) {
        found = nil
        chosen = []
        error = nil
        step = .review(brand)
        Task { await load(brand) }
    }

    /// The detected accounts of this bank. The ones with no answer yet start chosen.
    private func load(_ brand: BankBrand) async {
        let epoch = model.currentEpoch
        do {
            let identity = try await model.service.financialIdentity()
            guard epoch == model.currentEpoch else { return }
            let accounts = (identity.items ?? []).filter { BankGroup.groupID(of: $0) == brand.id && $0.ownership != .notMine }
            found = accounts
            chosen = Set(accounts.filter { $0.ownership == nil }.map(\.id))
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos leer tus cuentas.", "We couldn’t read your accounts."))
        }
    }

    // MARK: Review

    @ViewBuilder
    private func review(_ brand: BankBrand) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                if let error { ErrorStateView(message: error) { Task { await load(brand) } } }
                if let found {
                    if found.isEmpty {
                        Text(tx("Revisá tus cuentas", "Review your accounts")).font(.title2.weight(.bold)).foregroundStyle(.dincrText)
                        Text(tx("No encontré cuentas de \(brand.name) en tus correos. Podés agregarla a mano.",
                                "I found no \(brand.name) accounts in your mail. You can add one by hand."))
                            .font(DincrFont.body).foregroundStyle(.dincrText2)
                            .accessibilityIdentifier("addBank.none")
                    } else {
                        Text(tx("Revisá tus cuentas", "Review your accounts")).font(.title2.weight(.bold)).foregroundStyle(.dincrText)
                        Text(tx("Las encontré en tus correos. Marcá las que son tuyas.", "I found these in your mail. Check the ones that are yours."))
                            .font(DincrFont.body).foregroundStyle(.dincrText2)
                        OwnerGroup {
                            ForEach(Array(found.enumerated()), id: \.element.id) { index, account in
                                if index > 0 { OwnerDivider(inset: 0) }
                                row(account, brand: brand)
                            }
                        }
                    }
                    Button { manual = .some(brand) } label: { Text(tx("Agregar una a mano", "Add one by hand")) }
                        .buttonStyle(.dincrSecondary)
                        .accessibilityIdentifier("addBank.review.manual")
                } else if error == nil {
                    SkeletonView(rows: 2, showsFigure: false)
                }
            }
            .padding(DincrSpacing.s4)
        }
        .safeAreaInset(edge: .bottom) {
            if let found, !found.isEmpty {
                Button(tx("Agregar", "Add")) { Task { await add(found) } }
                    .buttonStyle(.dincrPrimary)
                    .disabled(saving || chosen.isEmpty && !found.contains { $0.ownership == .own })
                    .padding(DincrSpacing.s4)
                    .accessibilityIdentifier("addBank.add")
            }
        }
    }

    private func row(_ account: FinancialIdentity.Account, brand: BankBrand) -> some View {
        let own = account.ownership == .own
        let selected = own || chosen.contains(account.id)
        return Button {
            if chosen.contains(account.id) { chosen.remove(account.id) } else { chosen.insert(account.id) }
        } label: {
            HStack(spacing: DincrSpacing.s3) {
                Image(systemName: selected ? "checkmark.square.fill" : "square")
                    .font(.title3).foregroundStyle(selected ? OwnerColor.accent : OwnerColor.textMuted)
                    .accessibilityHidden(true)
                BankLogo(brand: brand, size: 44)
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.accountName ?? brand.name).font(DincrFont.body.weight(.semibold)).foregroundStyle(.dincrText)
                    Text(([account.maskedNumber, account.currency] + [own ? tx("Ya está agregada", "Already added") : nil]).compactMap { $0 }.joined(separator: " · "))
                        .font(DincrFont.caption).foregroundStyle(.dincrTextMuted)
                }
                Spacer(minLength: 0)
            }
            .frame(minHeight: 60)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(own)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("addBank.account.\(account.id)")
    }

    /// One ownership answer per chosen account, then the backend's list says what is now the Owner's.
    private func add(_ accounts: [FinancialIdentity.Account]) async {
        let epoch = model.currentEpoch
        saving = true; error = nil
        defer { saving = false }
        do {
            for id in chosen { try await model.service.setAccountOwnership(id: id, .own) }
            let identity = try await model.service.financialIdentity()
            guard epoch == model.currentEpoch else { return }
            let ids = Set(accounts.map(\.id))
            step = .done((identity.items ?? []).filter { ids.contains($0.id) && $0.ownership == .own })
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarlo.", "We couldn’t save it."))
        }
    }

    // MARK: By hand

    private struct ManualChoice: Identifiable {
        let brand: BankBrand?
        var id: String { brand?.id ?? "other" }
    }

    private var manualBinding: Binding<ManualChoice?> {
        Binding(get: { manual.map { ManualChoice(brand: $0) } }, set: { if $0 == nil { manual = nil } })
    }

    /// The codes the declaration knows by name; any other bank goes as "other" with its name.
    private static func declaredCode(_ brand: BankBrand?) -> String {
        guard let brand, ["bac", "popular", "multimoney"].contains(brand.id) else { return "other" }
        return brand.id
    }

    private static func declaredName(_ brand: BankBrand?) -> String {
        declaredCode(brand) == "other" ? (brand?.name ?? "") : ""
    }

    /// A saved declaration: back to its bank's accounts, or the whole list for another institution.
    private func showDeclared(_ brand: BankBrand?) async {
        manual = nil
        let epoch = model.currentEpoch
        guard let identity = try? await model.service.financialIdentity(), epoch == model.currentEpoch else {
            dismiss()
            return
        }
        let own = (identity.items ?? []).filter { $0.ownership == .own }
        if let brand {
            // Declared as "other", a bank is only recognizable by its name.
            step = .done(own.filter { BankGroup.groupID(of: $0) == brand.id || BankBrand.identify($0.bankName)?.id == brand.id })
        } else {
            dismiss()
        }
    }

    // MARK: Done

    private func done(_ accounts: [FinancialIdentity.Account]) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: DincrSpacing.s4) {
                    VStack(spacing: DincrSpacing.s2) {
                        Image(systemName: "checkmark.circle.fill").font(.system(size: 56)).foregroundStyle(OwnerColor.onHero).accessibilityHidden(true)
                        Text(accounts.count == 1 ? tx("1 cuenta en tu lista", "1 account on your list") : tx("\(accounts.count) cuentas en tu lista", "\(accounts.count) accounts on your list"))
                            .font(.title2.weight(.bold)).foregroundStyle(OwnerColor.onHero)
                            .accessibilityAddTraits(.isHeader)
                            .accessibilityIdentifier("addBank.done")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, DincrSpacing.s6)
                    .background(OwnerColor.hero, in: RoundedRectangle(cornerRadius: OwnerRadius.card, style: .continuous))
                    OwnerGroup {
                        ForEach(Array(accounts.enumerated()), id: \.element.id) { index, account in
                            if index > 0 { OwnerDivider(inset: 0) }
                            HStack(spacing: DincrSpacing.s3) {
                                BankLogo(brand: account.brand, size: 44)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(account.accountName ?? account.brand.name).font(DincrFont.body.weight(.semibold)).foregroundStyle(.dincrText)
                                    Text([account.maskedNumber, account.currency].compactMap { $0 }.joined(separator: " · "))
                                        .font(DincrFont.caption).foregroundStyle(.dincrTextMuted)
                                }
                                Spacer(minLength: 0)
                            }
                            .frame(minHeight: 60)
                            .accessibilityElement(children: .combine)
                        }
                    }
                }
                .padding(DincrSpacing.s4)
            }
            HStack(spacing: DincrSpacing.s3) {
                Button(tx("Agregar otra", "Add another")) { query = ""; step = .pick }
                    .buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("addBank.another")
                Button(tx("Listo", "Done")) { dismiss() }
                    .buttonStyle(.dincrPrimary)
                    .accessibilityIdentifier("addBank.finish")
            }
            .padding(DincrSpacing.s4)
        }
    }
}
