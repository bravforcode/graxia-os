import type { Meta, StoryObj } from '@storybook/react-vite'
import { Activity } from 'lucide-react'

import { MetricCard } from '@/components/ui/MetricCard'

const meta = {
  title: 'Primitives/MetricCard',
  component: MetricCard,
  args: {
    label: 'AI spend today',
    value: '$3.42',
    helper: '34% of the active daily budget.',
    accent: 'orange',
    icon: Activity,
  },
} satisfies Meta<typeof MetricCard>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Revenue: Story = {
  args: {
    label: 'Week revenue',
    value: '฿48,000',
    helper: '4 opportunities actioned this week.',
    accent: 'green',
  },
}
