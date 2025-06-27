"""
Database queries for billing and payment operations.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncpg
import logging

logger = logging.getLogger(__name__)

class BillingQueries:
    """Database queries for billing operations"""
    
    @staticmethod
    async def update_customer_stripe_id(
        conn: asyncpg.Connection,
        person_id: int,
        stripe_customer_id: str
    ) -> None:
        """Update a person's Stripe customer ID"""
        await conn.execute("""
            UPDATE people 
            SET stripe_customer_id = $1
            WHERE person_id = $2
        """, stripe_customer_id, person_id)
    
    @staticmethod
    async def get_person_by_stripe_customer_id(
        conn: asyncpg.Connection,
        stripe_customer_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get person by Stripe customer ID"""
        row = await conn.fetchrow("""
            SELECT p.*, cp.client_profile_id, cp.plan_type, 
                   cp.subscription_provider_id, cp.subscription_status
            FROM people p
            LEFT JOIN client_profiles cp ON p.person_id = cp.person_id
            WHERE p.stripe_customer_id = $1
        """, stripe_customer_id)
        return dict(row) if row else None
    
    @staticmethod
    async def create_payment_method(
        conn: asyncpg.Connection,
        person_id: int,
        stripe_payment_method_id: str,
        type: str,
        last4: Optional[str] = None,
        brand: Optional[str] = None,
        exp_month: Optional[int] = None,
        exp_year: Optional[int] = None,
        is_default: bool = False
    ) -> int:
        """Create a payment method record"""
        # If setting as default, unset other defaults first
        if is_default:
            await conn.execute("""
                UPDATE payment_methods 
                SET is_default = FALSE 
                WHERE person_id = $1
            """, person_id)
        
        row = await conn.fetchrow("""
            INSERT INTO payment_methods (
                person_id, stripe_payment_method_id, type, 
                last4, brand, exp_month, exp_year, is_default
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """, person_id, stripe_payment_method_id, type, 
            last4, brand, exp_month, exp_year, is_default)
        
        return row['id']
    
    @staticmethod
    async def get_payment_methods(
        conn: asyncpg.Connection,
        person_id: int
    ) -> List[Dict[str, Any]]:
        """Get all payment methods for a person"""
        rows = await conn.fetch("""
            SELECT * FROM payment_methods 
            WHERE person_id = $1 
            ORDER BY is_default DESC, created_at DESC
        """, person_id)
        return [dict(row) for row in rows]
    
    @staticmethod
    async def delete_payment_method(
        conn: asyncpg.Connection,
        person_id: int,
        stripe_payment_method_id: str
    ) -> bool:
        """Delete a payment method"""
        result = await conn.execute("""
            DELETE FROM payment_methods 
            WHERE person_id = $1 AND stripe_payment_method_id = $2
        """, person_id, stripe_payment_method_id)
        return result != 'DELETE 0'
    
    @staticmethod
    async def create_subscription_history(
        conn: asyncpg.Connection,
        client_profile_id: int,
        stripe_subscription_id: str,
        stripe_price_id: str,
        stripe_product_id: Optional[str],
        plan_type: str,
        status: str,
        current_period_start: datetime,
        current_period_end: datetime,
        **kwargs
    ) -> int:
        """Create a subscription history record"""
        row = await conn.fetchrow("""
            INSERT INTO subscription_history (
                client_profile_id, stripe_subscription_id, stripe_price_id,
                stripe_product_id, plan_type, status,
                current_period_start, current_period_end,
                cancel_at_period_end, canceled_at, trial_start, trial_end, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """, client_profile_id, stripe_subscription_id, stripe_price_id,
            stripe_product_id, plan_type, status,
            current_period_start, current_period_end,
            kwargs.get('cancel_at_period_end', False),
            kwargs.get('canceled_at'),
            kwargs.get('trial_start'),
            kwargs.get('trial_end'),
            kwargs.get('metadata', {}))
        
        return row['id']
    
    @staticmethod
    async def update_subscription_status(
        conn: asyncpg.Connection,
        stripe_subscription_id: str,
        status: str,
        **kwargs
    ) -> None:
        """Update subscription status in history"""
        query_parts = [
            "UPDATE subscription_history",
            "SET status = $2, updated_at = NOW()"
        ]
        params = [stripe_subscription_id, status]
        param_count = 2
        
        # Add optional fields
        optional_fields = [
            'cancel_at_period_end', 'canceled_at', 'ended_at',
            'current_period_start', 'current_period_end'
        ]
        
        for field in optional_fields:
            if field in kwargs:
                param_count += 1
                query_parts[1] += f", {field} = ${param_count}"
                params.append(kwargs[field])
        
        query_parts.append("WHERE stripe_subscription_id = $1")
        query = " ".join(query_parts)
        
        await conn.execute(query, *params)
    
    @staticmethod
    async def update_client_subscription(
        conn: asyncpg.Connection,
        client_profile_id: int,
        subscription_provider_id: str,
        subscription_status: str,
        subscription_ends_at: Optional[datetime],
        plan_type: str,
        plan_limits: Dict[str, int]
    ) -> None:
        """Update client profile with subscription information"""
        await conn.execute("""
            UPDATE client_profiles 
            SET subscription_provider_id = $1,
                subscription_status = $2,
                subscription_ends_at = $3,
                plan_type = $4,
                daily_discovery_allowance = $5,
                weekly_discovery_allowance = $6,
                updated_at = NOW()
            WHERE client_profile_id = $7
        """, subscription_provider_id, subscription_status, subscription_ends_at,
            plan_type, plan_limits['daily_discovery_allowance'],
            plan_limits['weekly_discovery_allowance'], client_profile_id)
    
    @staticmethod
    async def create_invoice(
        conn: asyncpg.Connection,
        person_id: int,
        stripe_invoice_id: str,
        stripe_subscription_id: Optional[str],
        invoice_number: Optional[str],
        amount_paid: int,
        amount_due: int,
        currency: str,
        status: str,
        **kwargs
    ) -> int:
        """Create an invoice record"""
        row = await conn.fetchrow("""
            INSERT INTO invoices (
                person_id, stripe_invoice_id, stripe_subscription_id,
                invoice_number, amount_paid, amount_due, currency, status,
                billing_reason, invoice_pdf, hosted_invoice_url,
                paid_at, due_date, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING id
        """, person_id, stripe_invoice_id, stripe_subscription_id,
            invoice_number, amount_paid, amount_due, currency, status,
            kwargs.get('billing_reason'),
            kwargs.get('invoice_pdf'),
            kwargs.get('hosted_invoice_url'),
            kwargs.get('paid_at'),
            kwargs.get('due_date'),
            kwargs.get('metadata', {}))
        
        return row['id']
    
    @staticmethod
    async def get_invoices(
        conn: asyncpg.Connection,
        person_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get invoices for a person"""
        rows = await conn.fetch("""
            SELECT * FROM invoices 
            WHERE person_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2 OFFSET $3
        """, person_id, limit, offset)
        return [dict(row) for row in rows]
    
    @staticmethod
    async def create_or_update_price_product(
        conn: asyncpg.Connection,
        stripe_product_id: str,
        stripe_price_id: str,
        plan_type: str,
        billing_period: str,
        amount: int,
        currency: str,
        active: bool = True,
        features: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """Create or update a price/product record"""
        row = await conn.fetchrow("""
            INSERT INTO price_products (
                stripe_product_id, stripe_price_id, plan_type,
                billing_period, amount, currency, active, features, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (stripe_price_id) 
            DO UPDATE SET
                stripe_product_id = EXCLUDED.stripe_product_id,
                plan_type = EXCLUDED.plan_type,
                billing_period = EXCLUDED.billing_period,
                amount = EXCLUDED.amount,
                currency = EXCLUDED.currency,
                active = EXCLUDED.active,
                features = EXCLUDED.features,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """, stripe_product_id, stripe_price_id, plan_type,
            billing_period, amount, currency, active,
            features or {}, metadata or {})
        
        return row['id']
    
    @staticmethod
    async def get_active_prices(
        conn: asyncpg.Connection
    ) -> List[Dict[str, Any]]:
        """Get all active price products"""
        rows = await conn.fetch("""
            SELECT * FROM price_products 
            WHERE active = TRUE 
            ORDER BY plan_type, billing_period
        """)
        return [dict(row) for row in rows]
    
    @staticmethod
    async def record_webhook_event(
        conn: asyncpg.Connection,
        stripe_event_id: str,
        event_type: str,
        payload: Dict[str, Any],
        processed: bool = False,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Record a webhook event for idempotency.
        Returns True if this is a new event, False if already processed.
        """
        try:
            await conn.execute("""
                INSERT INTO webhook_events (
                    stripe_event_id, event_type, payload, 
                    processed, error_message, processed_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """, stripe_event_id, event_type, payload,
                processed, error_message,
                datetime.now(timezone.utc) if processed else None)
            return True
        except asyncpg.UniqueViolationError:
            # Event already processed
            return False
    
    @staticmethod
    async def mark_webhook_processed(
        conn: asyncpg.Connection,
        stripe_event_id: str,
        error_message: Optional[str] = None
    ) -> None:
        """Mark a webhook event as processed"""
        await conn.execute("""
            UPDATE webhook_events 
            SET processed = TRUE,
                processed_at = NOW(),
                error_message = $2
            WHERE stripe_event_id = $1
        """, stripe_event_id, error_message)
    
    @staticmethod
    async def get_subscription_by_stripe_id(
        conn: asyncpg.Connection,
        stripe_subscription_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get subscription details by Stripe subscription ID"""
        row = await conn.fetchrow("""
            SELECT sh.*, cp.person_id, p.email, p.full_name
            FROM subscription_history sh
            JOIN client_profiles cp ON sh.client_profile_id = cp.client_profile_id
            JOIN people p ON cp.person_id = p.person_id
            WHERE sh.stripe_subscription_id = $1
            ORDER BY sh.created_at DESC
            LIMIT 1
        """, stripe_subscription_id)
        return dict(row) if row else None