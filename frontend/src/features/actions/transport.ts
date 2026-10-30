import { api, type SubscriptionCancelExecution, type WealthOrderExecution } from '@/lib/api'

export interface ActionTransport {
  step: (id: number, step: 'cancel' | 'confirm' | 'verification/start' | 'verification/verify', body?: object) => Promise<{ status: string; message: string }>
  executeTransfer: (id: number) => Promise<{ status: string; message: string }>
  executeCardLoss: (id: number) => Promise<{ status: string }>
  action: (id: number) => Promise<{ status: string }>
  executeWealthOrder?: (orderId: number) => Promise<WealthOrderExecution>
  executeSubscriptionCancel?: (actionId: number, subscriptionId: number) => Promise<SubscriptionCancelExecution>
}

export function serviceActionTransport(token: string): ActionTransport {
  return {
    step: (id, step, body) => api.actionStep(token, id, step, body),
    executeTransfer: (id) => api.executeTransfer(token, id),
    executeCardLoss: (id) => api.executeCardLoss(token, id),
    action: (id) => api.action(token, id),
    executeWealthOrder: (orderId) => api.executeWealthOrder(token, orderId),
    executeSubscriptionCancel: (actionId, subscriptionId) => api.executeSubscriptionCancel(token, actionId, subscriptionId),
  }
}
