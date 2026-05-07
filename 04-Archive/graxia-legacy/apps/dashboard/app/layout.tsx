import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CEO Dashboard | Graxia",
  description: "Enterprise Control Center for Graxia OS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 text-gray-900 antialiased`}>
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar */}
          <aside className="w-64 bg-gray-900 text-white flex flex-col">
            <div className="p-6">
              <h1 className="text-2xl font-bold tracking-wider">GRAXIA OS</h1>
              <p className="text-sm text-gray-400 mt-1">CEO Control Center</p>
            </div>
            <nav className="flex-1 px-4 space-y-2 mt-4">
              <a href="#" className="block px-4 py-2 bg-gray-800 rounded-md text-white font-medium">Dashboard</a>
              <a href="#" className="block px-4 py-2 text-gray-400 hover:bg-gray-800 hover:text-white rounded-md transition-colors">Sales Pipeline</a>
              <a href="#" className="block px-4 py-2 text-gray-400 hover:bg-gray-800 hover:text-white rounded-md transition-colors">AI Agents</a>
              <a href="#" className="block px-4 py-2 text-gray-400 hover:bg-gray-800 hover:text-white rounded-md transition-colors">Settings</a>
            </nav>
            <div className="p-4 border-t border-gray-800">
              <div className="flex items-center">
                <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-sm font-bold">C</div>
                <div className="ml-3">
                  <p className="text-sm font-medium">Chief Executive</p>
                </div>
              </div>
            </div>
          </aside>
          
          {/* Main Content */}
          <main className="flex-1 overflow-y-auto bg-gray-50">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
