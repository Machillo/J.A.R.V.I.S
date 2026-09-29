import Foundation

/// The release identity of the native iOS app: the same one as the store app it replaces
/// (Capacitor `frontend/ios-dincr`). Pinned by `IdentityGuardTests`, which also read
/// `Config/Base.xcconfig`, so the build can never drift back to a side-by-side identity.
public enum AppIdentity {
    public static let bundleID = "com.dincr.app"
    /// Supabase OAuth return. It is the redirect the Capacitor app already uses in production, so it
    /// is in the Supabase allowlist; the native app catches it inside `ASWebAuthenticationSession`.
    public static let authCallbackScheme = "com.dincr.app"
    public static let authRedirect = "com.dincr.app://auth/callback"
}
