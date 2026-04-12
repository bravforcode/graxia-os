import type { Meta, StoryObj } from '@storybook/react-vite'

import { NoticeBanner } from '@/components/ui/NoticeBanner'

const meta = {
  title: 'Primitives/NoticeBanner',
  component: NoticeBanner,
  args: {
    tone: 'success',
    message: 'Draft approved and queued for the next execution window.',
  },
  argTypes: {
    onDismiss: { action: 'dismissed' },
  },
} satisfies Meta<typeof NoticeBanner>

export default meta

type Story = StoryObj<typeof meta>

export const Success: Story = {}

export const Warning: Story = {
  args: {
    tone: 'warning',
    message: 'Fallback mode is active. Review generated output before sending.',
  },
}

export const Danger: Story = {
  args: {
    tone: 'danger',
    message: 'Approval failed. Retry after checking runtime health.',
  },
}
