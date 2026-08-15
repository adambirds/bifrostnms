import type {Metadata} from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'BifrostNMS Account',
  description: 'Authentication for BifrostNMS',
}

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
