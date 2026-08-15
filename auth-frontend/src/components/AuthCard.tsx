export default function AuthCard({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <main className="auth-shell">
      <section className="card">
        <div className="brand">
          <div className="brand-mark">B</div>
          <div>
            <strong>BifrostNMS</strong>
            <div className="muted">See your network from everywhere.</div>
          </div>
        </div>
        {children}
      </section>
    </main>
  )
}
