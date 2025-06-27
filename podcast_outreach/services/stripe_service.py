"""
Stripe integration service for handling payments, subscriptions, and billing.
"""

import os
import stripe
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Initialize Stripe with secret key
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

class StripeService:
    """Service for handling Stripe operations"""
    
    @staticmethod
    async def create_customer(email: str, name: Optional[str] = None, 
                            metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Create a new Stripe customer.
        
        Args:
            email: Customer email
            name: Customer full name
            metadata: Additional metadata to store with customer
            
        Returns:
            Stripe customer object
        """
        try:
            customer_data = {
                'email': email,
                'metadata': metadata or {}
            }
            if name:
                customer_data['name'] = name
                
            customer = stripe.Customer.create(**customer_data)
            logger.info(f"Created Stripe customer: {customer.id}")
            return customer
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {str(e)}")
            raise
    
    @staticmethod
    async def create_checkout_session(
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, str]] = None,
        allow_promotion_codes: bool = True,
        trial_period_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for subscription.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID for the subscription
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if customer cancels
            metadata: Additional metadata for the session
            allow_promotion_codes: Whether to allow promo codes
            trial_period_days: Number of trial days
            
        Returns:
            Stripe checkout session object
        """
        try:
            session_data = {
                'customer': customer_id,
                'payment_method_types': ['card'],
                'line_items': [{
                    'price': price_id,
                    'quantity': 1,
                }],
                'mode': 'subscription',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'allow_promotion_codes': allow_promotion_codes,
                'metadata': metadata or {},
                'subscription_data': {
                    'metadata': metadata or {}
                }
            }
            
            if trial_period_days:
                session_data['subscription_data']['trial_period_days'] = trial_period_days
            
            session = stripe.checkout.Session.create(**session_data)
            logger.info(f"Created checkout session: {session.id}")
            return session
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {str(e)}")
            raise
    
    @staticmethod
    async def create_billing_portal_session(
        customer_id: str,
        return_url: str
    ) -> Dict[str, Any]:
        """
        Create a Stripe billing portal session for customer self-service.
        
        Args:
            customer_id: Stripe customer ID
            return_url: URL to return to after portal session
            
        Returns:
            Stripe billing portal session object
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            logger.info(f"Created billing portal session for customer: {customer_id}")
            return session
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create billing portal session: {str(e)}")
            raise
    
    @staticmethod
    async def get_subscription(subscription_id: str) -> Dict[str, Any]:
        """
        Retrieve a subscription from Stripe.
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            Stripe subscription object
        """
        try:
            subscription = stripe.Subscription.retrieve(
                subscription_id,
                expand=['latest_invoice.payment_intent', 'customer', 'default_payment_method']
            )
            return subscription
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve subscription: {str(e)}")
            raise
    
    @staticmethod
    async def cancel_subscription(
        subscription_id: str,
        cancel_at_period_end: bool = True
    ) -> Dict[str, Any]:
        """
        Cancel a subscription.
        
        Args:
            subscription_id: Stripe subscription ID
            cancel_at_period_end: If True, cancel at end of billing period
            
        Returns:
            Updated subscription object
        """
        try:
            if cancel_at_period_end:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
            else:
                subscription = stripe.Subscription.delete(subscription_id)
            
            logger.info(f"Cancelled subscription: {subscription_id}")
            return subscription
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {str(e)}")
            raise
    
    @staticmethod
    async def update_subscription(
        subscription_id: str,
        price_id: str,
        proration_behavior: str = 'create_prorations'
    ) -> Dict[str, Any]:
        """
        Update a subscription to a different price/plan.
        
        Args:
            subscription_id: Stripe subscription ID
            price_id: New Stripe price ID
            proration_behavior: How to handle prorations
            
        Returns:
            Updated subscription object
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            updated_subscription = stripe.Subscription.modify(
                subscription_id,
                items=[{
                    'id': subscription['items']['data'][0].id,
                    'price': price_id,
                }],
                proration_behavior=proration_behavior
            )
            
            logger.info(f"Updated subscription {subscription_id} to price {price_id}")
            return updated_subscription
        except stripe.error.StripeError as e:
            logger.error(f"Failed to update subscription: {str(e)}")
            raise
    
    @staticmethod
    async def list_invoices(
        customer_id: str,
        limit: int = 10,
        starting_after: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List invoices for a customer.
        
        Args:
            customer_id: Stripe customer ID
            limit: Maximum number of invoices to return
            starting_after: Pagination cursor
            
        Returns:
            List of invoice objects
        """
        try:
            params = {
                'customer': customer_id,
                'limit': limit
            }
            if starting_after:
                params['starting_after'] = starting_after
                
            invoices = stripe.Invoice.list(**params)
            return invoices.data
        except stripe.error.StripeError as e:
            logger.error(f"Failed to list invoices: {str(e)}")
            raise
    
    @staticmethod
    async def create_or_update_payment_method(
        customer_id: str,
        payment_method_id: str,
        set_as_default: bool = True
    ) -> Dict[str, Any]:
        """
        Attach a payment method to a customer and optionally set as default.
        
        Args:
            customer_id: Stripe customer ID
            payment_method_id: Stripe payment method ID
            set_as_default: Whether to set as default payment method
            
        Returns:
            Payment method object
        """
        try:
            # Attach payment method to customer
            payment_method = stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer_id
            )
            
            # Set as default if requested
            if set_as_default:
                stripe.Customer.modify(
                    customer_id,
                    invoice_settings={
                        'default_payment_method': payment_method_id
                    }
                )
            
            logger.info(f"Attached payment method {payment_method_id} to customer {customer_id}")
            return payment_method
        except stripe.error.StripeError as e:
            logger.error(f"Failed to attach payment method: {str(e)}")
            raise
    
    @staticmethod
    async def verify_webhook_signature(
        payload: bytes,
        signature: str,
        webhook_secret: str
    ) -> Dict[str, Any]:
        """
        Verify Stripe webhook signature and return event.
        
        Args:
            payload: Raw request body
            signature: Stripe signature header
            webhook_secret: Webhook endpoint secret
            
        Returns:
            Stripe event object
            
        Raises:
            ValueError: If signature verification fails
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            return event
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {str(e)}")
            raise
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {str(e)}")
            raise ValueError("Invalid webhook signature")
    
    @staticmethod
    def map_stripe_plan_to_internal(stripe_price_id: str) -> str:
        """
        Map Stripe price ID to internal plan type.
        
        Args:
            stripe_price_id: Stripe price ID
            
        Returns:
            Internal plan type ('free', 'paid_basic', 'paid_premium')
        """
        # This mapping should be configured based on your Stripe products
        price_mapping = {
            os.getenv('STRIPE_PRICE_BASIC_MONTHLY'): 'paid_basic',
            os.getenv('STRIPE_PRICE_BASIC_YEARLY'): 'paid_basic',
            os.getenv('STRIPE_PRICE_PREMIUM_MONTHLY'): 'paid_premium',
            os.getenv('STRIPE_PRICE_PREMIUM_YEARLY'): 'paid_premium',
        }
        
        return price_mapping.get(stripe_price_id, 'free')
    
    @staticmethod
    def get_plan_limits(plan_type: str) -> Dict[str, int]:
        """
        Get discovery limits for a plan type.
        
        Args:
            plan_type: Internal plan type
            
        Returns:
            Dictionary with daily and weekly limits
        """
        limits = {
            'free': {
                'daily_discovery_allowance': 10,
                'weekly_discovery_allowance': 50
            },
            'paid_basic': {
                'daily_discovery_allowance': 100,
                'weekly_discovery_allowance': 500
            },
            'paid_premium': {
                'daily_discovery_allowance': 500,
                'weekly_discovery_allowance': 2500
            }
        }
        
        return limits.get(plan_type, limits['free'])