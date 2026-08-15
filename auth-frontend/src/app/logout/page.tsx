'use client'

import {useEffect} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest} from '@/lib/api'

export default function LogoutPage() {
  useEffect(() => {
    authRequest('/auth/logout', {method: 'POST'}).finally(() => { window.location.href = '/login' })
  }, [])
  return <AuthCard><h1>Signing out…</h1><p className="muted">Ending your BifrostNMS session.</p></AuthCard>
}
