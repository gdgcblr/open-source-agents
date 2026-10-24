import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Page not found</h1>
      <p className="mt-2 text-ink-muted">
        This address doesn’t match any page.{' '}
        <Link to="/calls" className="font-semibold text-ink underline underline-offset-4">
          Go to all calls
        </Link>
      </p>
    </>
  )
}
