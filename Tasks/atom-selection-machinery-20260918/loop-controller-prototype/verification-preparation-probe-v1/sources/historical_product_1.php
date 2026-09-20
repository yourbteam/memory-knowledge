<?php

namespace App\Services;

use Illuminate\Database\ConnectionInterface;

class TourDiscountPrerequisites
{
    private $connection;

    public function __construct(ConnectionInterface $connection)
    {
        $this->connection = $connection;
    }

    public function isConfigured($checkoutTourId): bool
    {
        return $this->connection->table('tour_discount_prerequisites')
            ->where('checkout_tour_id', $checkoutTourId)
            ->exists();
    }

    public function getPrerequisiteTourIds($checkoutTourId): array
    {
        return $this->connection->table('tour_discount_prerequisites')
            ->where('checkout_tour_id', $checkoutTourId)
            ->pluck('prerequisite_tour_id')
            ->map(function ($tourId) {
                return (int) $tourId;
            })
            ->all();
    }
}
