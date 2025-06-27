"""
API endpoints for billing and subscription management.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any
import os
import logging
from datetime import datetime, timezone

from ..dependencies import get_current_user
from ...database.connection import get_db_pool
from ...database.queries.billing import BillingQueries
from ...services.stripe_service import StripeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

# Request/Response Models
class CheckoutSessionRequest(BaseModel):
    plan_type: str = Field(..., description="Plan type: 'paid_basic' or 'paid_premium'")
    billing_period: str = Field(..., description="Billing period: 'monthly' or 'yearly'")
    success_url: Optional[str] = Field(None, description="URL to redirect after successful payment")
    cancel_url: Optional[str] = Field(None, description="URL to redirect if customer cancels")

class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str

class SubscriptionResponse(BaseModel):
    subscription_id: Optional[str]
    plan_type: str
    status: str
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool = False
    payment_method: Optional[Dict[str, Any]]

class InvoiceResponse(BaseModel):
    invoice_id: str
    amount_paid: int
    currency: str
    status: str
    invoice_pdf: Optional[str]
    created_at: datetime

class PaymentMethodResponse(BaseModel):
    id: int
    payment_method_id: str
    type: str
    last4: Optional[str]
    brand: Optional[str]
    exp_month: Optional[int]
    exp_year: Optional[int]
    is_default: bool

@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a Stripe checkout session for subscription upgrade."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Get or create Stripe customer
            if not current_user.get('stripe_customer_id'):
                customer = await StripeService.create_customer(
                    email=current_user['email'],
                    name=current_user.get('full_name'),
                    metadata={'person_id': str(current_user['person_id'])}
                )
                await BillingQueries.update_customer_stripe_id(
                    conn, current_user['person_id'], customer.id
                )
                stripe_customer_id = customer.id
            else:
                stripe_customer_id = current_user['stripe_customer_id']
            
            # Map plan type and billing period to Stripe price ID
            price_key = f"STRIPE_PRICE_{request.plan_type.upper()}_{request.billing_period.upper()}"
            price_id = os.getenv(price_key)
            
            if not price_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid plan type or billing period combination"
                )
            
            # Create checkout session
            base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
            success_url = request.success_url or f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = request.cancel_url or f"{base_url}/billing"
            
            session = await StripeService.create_checkout_session(
                customer_id=stripe_customer_id,
                price_id=price_id,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'person_id': str(current_user['person_id']),
                    'plan_type': request.plan_type
                }
            )
            
            return CheckoutSessionResponse(
                checkout_url=session.url,
                session_id=session.id
            )
            
        except Exception as e:
            logger.error(f"Failed to create checkout session: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to create checkout session")

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(current_user: dict = Depends(get_current_user)):
    """Get current subscription details."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Get client profile
            client_profile = await conn.fetchrow("""
                SELECT * FROM client_profiles WHERE person_id = $1
            """, current_user['person_id'])
            
            if not client_profile:
                return SubscriptionResponse(
                    subscription_id=None,
                    plan_type='free',
                    status='inactive',
                    current_period_end=None
                )
            
            response = SubscriptionResponse(
                subscription_id=client_profile['subscription_provider_id'],
                plan_type=client_profile['plan_type'],
                status=client_profile['subscription_status'] or 'inactive',
                current_period_end=client_profile['subscription_ends_at']
            )
            
            # If there's an active subscription, get details from Stripe
            if client_profile['subscription_provider_id']:
                try:
                    subscription = await StripeService.get_subscription(
                        client_profile['subscription_provider_id']
                    )
                    response.cancel_at_period_end = subscription.cancel_at_period_end
                    
                    # Get default payment method
                    if subscription.default_payment_method:
                        pm = subscription.default_payment_method
                        response.payment_method = {
                            'type': pm.type,
                            'last4': pm.card.last4 if hasattr(pm, 'card') else None,
                            'brand': pm.card.brand if hasattr(pm, 'card') else None
                        }
                except Exception as e:
                    logger.error(f"Failed to fetch Stripe subscription: {str(e)}")
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to get subscription: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to get subscription details")

@router.post("/cancel-subscription")
async def cancel_subscription(
    cancel_immediately: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """Cancel subscription at end of billing period or immediately."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Get client profile
            client_profile = await conn.fetchrow("""
                SELECT * FROM client_profiles WHERE person_id = $1
            """, current_user['person_id'])
            
            if not client_profile or not client_profile['subscription_provider_id']:
                raise HTTPException(status_code=404, detail="No active subscription found")
            
            # Cancel in Stripe
            subscription = await StripeService.cancel_subscription(
                client_profile['subscription_provider_id'],
                cancel_at_period_end=not cancel_immediately
            )
            
            # Update database
            if cancel_immediately:
                await BillingQueries.update_client_subscription(
                    conn,
                    client_profile['client_profile_id'],
                    subscription.id,
                    'canceled',
                    None,
                    'free',
                    StripeService.get_plan_limits('free')
                )
            else:
                # Just update the subscription status
                await conn.execute("""
                    UPDATE client_profiles 
                    SET subscription_status = 'active_until_end'
                    WHERE client_profile_id = $1
                """, client_profile['client_profile_id'])
            
            return {"message": "Subscription cancelled successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel subscription: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to cancel subscription")

@router.get("/portal-session")
async def create_portal_session(
    return_url: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Create a Stripe billing portal session for customer self-service."""
    try:
        if not current_user.get('stripe_customer_id'):
            raise HTTPException(status_code=404, detail="No billing account found")
        
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        return_url = return_url or f"{base_url}/billing"
        
        session = await StripeService.create_billing_portal_session(
            current_user['stripe_customer_id'],
            return_url
        )
        
        # Return redirect response
        return RedirectResponse(url=session.url, status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create portal session: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create billing portal session")

@router.get("/invoices", response_model=List[InvoiceResponse])
async def list_invoices(
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """List invoices for the current user."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            invoices = await BillingQueries.get_invoices(
                conn, current_user['person_id'], limit, offset
            )
            
            return [
                InvoiceResponse(
                    invoice_id=inv['stripe_invoice_id'],
                    amount_paid=inv['amount_paid'],
                    currency=inv['currency'],
                    status=inv['status'],
                    invoice_pdf=inv['invoice_pdf'],
                    created_at=inv['created_at']
                )
                for inv in invoices
            ]
            
        except Exception as e:
            logger.error(f"Failed to list invoices: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to list invoices")

@router.get("/payment-methods", response_model=List[PaymentMethodResponse])
async def list_payment_methods(current_user: dict = Depends(get_current_user)):
    """List payment methods for the current user."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            methods = await BillingQueries.get_payment_methods(
                conn, current_user['person_id']
            )
            
            return [
                PaymentMethodResponse(
                    id=method['id'],
                    payment_method_id=method['stripe_payment_method_id'],
                    type=method['type'],
                    last4=method['last4'],
                    brand=method['brand'],
                    exp_month=method['exp_month'],
                    exp_year=method['exp_year'],
                    is_default=method['is_default']
                )
                for method in methods
            ]
            
        except Exception as e:
            logger.error(f"Failed to list payment methods: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to list payment methods")

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """Handle Stripe webhook events."""
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    if not webhook_secret:
        logger.error("Stripe webhook secret not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    
    try:
        # Get raw body
        payload = await request.body()
        
        # Verify webhook signature
        event = await StripeService.verify_webhook_signature(
            payload, stripe_signature, webhook_secret
        )
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Check if we've already processed this event
            is_new_event = await BillingQueries.record_webhook_event(
                conn, event['id'], event['type'], event
            )
            
            if not is_new_event:
                logger.info(f"Webhook event {event['id']} already processed")
                return {"received": True}
            
            try:
                # Handle different event types
                if event['type'] == 'customer.subscription.created':
                    await handle_subscription_created(conn, event['data']['object'])
                
                elif event['type'] == 'customer.subscription.updated':
                    await handle_subscription_updated(conn, event['data']['object'])
                
                elif event['type'] == 'customer.subscription.deleted':
                    await handle_subscription_deleted(conn, event['data']['object'])
                
                elif event['type'] == 'invoice.paid':
                    await handle_invoice_paid(conn, event['data']['object'])
                
                elif event['type'] == 'invoice.payment_failed':
                    await handle_invoice_payment_failed(conn, event['data']['object'])
                
                # Mark as processed
                await BillingQueries.mark_webhook_processed(conn, event['id'])
                
            except Exception as e:
                logger.error(f"Error processing webhook event {event['id']}: {str(e)}")
                await BillingQueries.mark_webhook_processed(
                    conn, event['id'], error_message=str(e)
                )
                raise
        
        return {"received": True}
        
    except ValueError as e:
        logger.error(f"Invalid webhook signature: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# Webhook event handlers
async def handle_subscription_created(conn, subscription):
    """Handle new subscription creation."""
    customer_id = subscription['customer']
    
    # Get person by Stripe customer ID
    person = await BillingQueries.get_person_by_stripe_customer_id(conn, customer_id)
    if not person:
        logger.error(f"No person found for Stripe customer {customer_id}")
        return
    
    # Map plan type
    price_id = subscription['items']['data'][0]['price']['id']
    plan_type = StripeService.map_stripe_plan_to_internal(price_id)
    plan_limits = StripeService.get_plan_limits(plan_type)
    
    # Create subscription history
    await BillingQueries.create_subscription_history(
        conn,
        person['client_profile_id'],
        subscription['id'],
        price_id,
        subscription['items']['data'][0]['price'].get('product'),
        plan_type,
        subscription['status'],
        datetime.fromtimestamp(subscription['current_period_start'], tz=timezone.utc),
        datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc),
        cancel_at_period_end=subscription.get('cancel_at_period_end', False),
        trial_start=datetime.fromtimestamp(subscription['trial_start'], tz=timezone.utc) if subscription.get('trial_start') else None,
        trial_end=datetime.fromtimestamp(subscription['trial_end'], tz=timezone.utc) if subscription.get('trial_end') else None
    )
    
    # Update client profile
    await BillingQueries.update_client_subscription(
        conn,
        person['client_profile_id'],
        subscription['id'],
        subscription['status'],
        datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc),
        plan_type,
        plan_limits
    )

async def handle_subscription_updated(conn, subscription):
    """Handle subscription updates."""
    # Similar to created, but update existing records
    await handle_subscription_created(conn, subscription)
    
    # Update subscription history status
    await BillingQueries.update_subscription_status(
        conn,
        subscription['id'],
        subscription['status'],
        cancel_at_period_end=subscription.get('cancel_at_period_end', False),
        canceled_at=datetime.fromtimestamp(subscription['canceled_at'], tz=timezone.utc) if subscription.get('canceled_at') else None,
        current_period_start=datetime.fromtimestamp(subscription['current_period_start'], tz=timezone.utc),
        current_period_end=datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc)
    )

async def handle_subscription_deleted(conn, subscription):
    """Handle subscription cancellation/deletion."""
    customer_id = subscription['customer']
    
    # Get person by Stripe customer ID
    person = await BillingQueries.get_person_by_stripe_customer_id(conn, customer_id)
    if not person:
        return
    
    # Update subscription history
    await BillingQueries.update_subscription_status(
        conn,
        subscription['id'],
        'canceled',
        ended_at=datetime.now(timezone.utc)
    )
    
    # Reset to free plan
    await BillingQueries.update_client_subscription(
        conn,
        person['client_profile_id'],
        None,  # Clear subscription ID
        'canceled',
        None,  # Clear end date
        'free',
        StripeService.get_plan_limits('free')
    )

async def handle_invoice_paid(conn, invoice):
    """Handle successful invoice payment."""
    customer_id = invoice['customer']
    
    # Get person by Stripe customer ID
    person = await BillingQueries.get_person_by_stripe_customer_id(conn, customer_id)
    if not person:
        return
    
    # Create invoice record
    await BillingQueries.create_invoice(
        conn,
        person['person_id'],
        invoice['id'],
        invoice.get('subscription'),
        invoice.get('number'),
        invoice['amount_paid'],
        invoice['amount_due'],
        invoice['currency'],
        'paid',
        billing_reason=invoice.get('billing_reason'),
        invoice_pdf=invoice.get('invoice_pdf'),
        hosted_invoice_url=invoice.get('hosted_invoice_url'),
        paid_at=datetime.fromtimestamp(invoice['status_transitions']['paid_at'], tz=timezone.utc) if invoice.get('status_transitions', {}).get('paid_at') else None,
        due_date=datetime.fromtimestamp(invoice['due_date'], tz=timezone.utc) if invoice.get('due_date') else None
    )

async def handle_invoice_payment_failed(conn, invoice):
    """Handle failed invoice payment."""
    # Similar to paid, but with failed status
    customer_id = invoice['customer']
    
    person = await BillingQueries.get_person_by_stripe_customer_id(conn, customer_id)
    if not person:
        return
    
    await BillingQueries.create_invoice(
        conn,
        person['person_id'],
        invoice['id'],
        invoice.get('subscription'),
        invoice.get('number'),
        0,  # No amount paid
        invoice['amount_due'],
        invoice['currency'],
        'payment_failed',
        billing_reason=invoice.get('billing_reason')
    )
    
    # Update subscription status if applicable
    if invoice.get('subscription') and person.get('client_profile_id'):
        await conn.execute("""
            UPDATE client_profiles 
            SET subscription_status = 'past_due'
            WHERE client_profile_id = $1
        """, person['client_profile_id'])