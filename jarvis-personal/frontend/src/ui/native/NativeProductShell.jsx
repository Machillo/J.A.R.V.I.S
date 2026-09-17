import { nativePlatformClass } from "./platform";

export default function NativeProductShell({ product, platform, plan = "personal", className = "", children }) {
  const safePlan = String(plan || "personal").toLowerCase();

  return (
    <div
      className={`${nativePlatformClass(platform)} native-product native-product--${product} native-plan--${safePlan} ${className}`.trim()}
      data-product={product}
      data-platform={platform}
      data-plan={safePlan}
    >
      {children}
    </div>
  );
}
