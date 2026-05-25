import type { Meta, StoryObj } from '@storybook/react-vite'

import { EmptyState } from '@/components/ui/empty-state'

const meta = {
  title: 'Primitives/EmptyState',
  component: EmptyState,
  args: {
    message: 'No high-priority opportunities are currently queued.',
  },
} satisfies Meta<typeof EmptyState>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Loading: Story = {
  args: {
    message: 'Loading drafts...',
  },
}
