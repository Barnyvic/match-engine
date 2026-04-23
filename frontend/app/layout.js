import "./globals.css";

export const metadata = {
  title: "Match Engine",
  description: "Premium football prediction intelligence dashboard"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
