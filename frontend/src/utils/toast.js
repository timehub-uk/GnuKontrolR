import { toast } from 'sonner';
export { toast };
export const toastSuccess = (msg, opts) => toast.success(msg, { duration: 3000, ...opts });
export const toastError = (msg, opts) => toast.error(msg, { duration: 5000, ...opts });
export const toastWarning = (msg, opts) => toast.warning(msg, { duration: 4000, ...opts });
export const toastInfo = (msg, opts) => toast.message(msg, { duration: 3000, ...opts });
export const toastLoading = (msg, opts) => toast.loading(msg, { ...opts });
export const toastDismiss = (id) => toast.dismiss(id);
