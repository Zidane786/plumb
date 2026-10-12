import "./globals.css";

export const metadata = { title: "Tasks" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-background text-on-surface">{children}</body>
    </html>
  );
}
