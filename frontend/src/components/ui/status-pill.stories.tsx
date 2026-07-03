import type { Meta, StoryObj } from '@storybook/react-vite'

import { StatusPill } from '@/components/ui/status-pill'

const meta = {
  title: 'Primitives/StatusPill',
  component: StatusPill,
  args: {
    label: 'Live',
    tone: 'success',
    pulse: true,
  },
} satisfies Meta<typeof StatusPill>

export default meta

type Story = StoryObj<typeof meta>

export const Live: Story = {}

export const Fallback: Story = {
  args: {
    label: 'Fallback',
    tone: 'warning',
    pulse: false,
  },
}

export const Offline: Story = {
  args: {
    label: 'Offline',
    tone: 'danger',
    pulse: false,
  },
}
