'use client'

import {useRouter} from 'next/navigation'
import {useEffect} from 'react'
import AuthCard from '@/components/AuthCard'
import {authRequest} from '@/lib/api'

export default function LogoutPage() {
  const router = useRouter()

  useEffect(() => {
    authRequest('/auth/logout', {method: 'POST'}).finally(() => {
      router.replace('/login')
    })
  }, [router])

  return <AuthCard><h1>Signing out…</h1><p className="muted">Ending your BifrostNMS session.</p></AuthCard>
}
