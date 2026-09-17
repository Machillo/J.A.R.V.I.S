import { nativePlatformClass } from "./platform";

export default function NativeProductShell({ product, platform, className = "", children }) {
  return (
    <div
      className={`${nativePlatformClass(platform)} native-product native-product--${product} ${className}`.trim()}
      data-product={product}
      data-platform={platform}
    >
      {children}
    </div>
  );
}
