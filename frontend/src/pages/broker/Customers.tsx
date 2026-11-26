import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Customer } from '../../lib/api'
import { Button, Card, ErrorNote, Field, Icon, Input, Modal, PageTitle } from '../../components/ui'

interface Created { customer: Customer; login: { email: string; temporary_password: string } }

export default function Customers() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['customers'], queryFn: () => api<Customer[]>('/customers') })
  const [open, setOpen] = useState(false)
  const [created, setCreated] = useState<Created | null>(null)
  const m = useMutation({
    mutationFn: (body: { name: string; contact_name: string; email: string }) => api<Created>('/customers', { body }),
    onSuccess: (r) => { setCreated(r); qc.invalidateQueries({ queryKey: ['customers'] }) },
  })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget)
    m.mutate({ name: String(f.get('name')), contact_name: String(f.get('contact')), email: String(f.get('email')) })
  }
  return (
    <>
      <div className="flex items-end justify-between">
        <PageTitle sub="Each customer gets a portal login to pay and read their statement.">Customers</PageTitle>
        <Button onClick={() => { setOpen(true); setCreated(null); m.reset() }}><Icon name="add" /> New customer</Button>
      </div>
      <Card className="divide-y divide-line">
        {q.data?.map((c) => (
          <div key={c.id} className="px-5 py-3.5 flex items-center justify-between">
            <div><div className="font-medium">{c.name}</div><div className="text-body text-[13px]">{c.contact_name} · {c.email}</div></div>
          </div>
        ))}
      </Card>
      {open && (
        <Modal title={created ? 'Customer created' : 'New customer'} onClose={() => setOpen(false)}>
          {created ? (
            <div className="space-y-3">
              <p>Portal login created for <b>{created.customer.name}</b>. Share these sandbox credentials (shown once):</p>
              <div className="rounded-corgi bg-canvas p-3 mono !text-[13px]">{created.login.email}<br />{created.login.temporary_password}</div>
              <p className="text-[12px] text-muted">A production system would send an invite link instead of a temporary password.</p>
              <Button onClick={() => setOpen(false)}>Done</Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <Field label="Company name"><Input name="name" required /></Field>
              <Field label="Contact name"><Input name="contact" required /></Field>
              <Field label="Contact email"><Input name="email" type="email" required /></Field>
              <ErrorNote error={m.error} />
              <Button disabled={m.isPending}>Create customer</Button>
            </form>
          )}
        </Modal>
      )}
    </>
  )
}
