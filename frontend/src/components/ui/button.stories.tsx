import type { Meta, StoryObj } from '@storybook/react-vite'
import { Save, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/Button'

const meta = {
  title: 'Primitives/Button',
  component: Button,
  args: {
    children: 'Run action',
    variant: 'primary',
    size: 'md',
    loading: false,
  },
  argTypes: {
    onClick: { action: 'clicked' },
  },
} satisfies Meta<typeof Button>

export default meta

type Story = StoryObj<typeof meta>

export const Primary: Story = {
  args: {
    children: 'Launch scan',
    icon: <Sparkles size={16} />,
  },
}

export const Secondary: Story = {
  args: {
    children: 'Save draft',
    icon: <Save size={16} />,
    variant: 'secondary',
  },
}

export const Loading: Story = {
  args: {
    children: 'Saving',
    loading: true,
  },
}
