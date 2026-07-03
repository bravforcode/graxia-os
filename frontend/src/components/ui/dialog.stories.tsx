import { useState, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'

import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'

const meta: Meta<typeof Dialog> = {
  title: 'Primitives/Dialog',
  component: Dialog,
  args: {
    open: true,
    
    description: 'Capture operator context before removing this draft from the active queue.',
    onClose: () => {},
    children: null,
  },
  parameters: {
    layout: 'fullscreen',
  },
}

export default meta

type Story = StoryObj<typeof meta>

type DialogStoryArgs = ComponentProps<typeof Dialog>

function DialogStoryDemo(args: DialogStoryArgs) {
  const [open, setOpen] = useState(true)

  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <Button onClick={() => setOpen(true)}>Open dialog</Button>
      <Dialog
        {...args}
        open={open}
        
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Confirm rejection
            </Button>
          </>
        }
      >
        <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>Reason</span>
          <textarea
            className="input-field min-h-28 resize-y"
            defaultValue="The draft needs a tighter opening and a more specific call to action."
          />
        </label>
      </Dialog>
    </div>
  )
}

export const Default: Story = {
  render: (args: DialogStoryArgs) => <DialogStoryDemo {...args} />,
}
