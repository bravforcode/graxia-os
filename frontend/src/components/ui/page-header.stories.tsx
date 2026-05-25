import type { Meta, StoryObj } from '@storybook/react-vite'
import { RefreshCw, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/ui/page-header'

const meta = {
  title: 'Primitives/PageHeader',
  component: PageHeader,
  args: {
    eyebrow: 'Approval lane',
    title: 'Draft queue',
    description: 'Review generated drafts before they move into the outside world.',
  },
} satisfies Meta<typeof PageHeader>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithActions: Story = {
  args: {
    actions: (
      <>
        <Button variant="secondary" icon={<RefreshCw size={16} />}>
          Refresh
        </Button>
        <Button icon={<Sparkles size={16} />}>Generate brief</Button>
      </>
    ),
  },
}
