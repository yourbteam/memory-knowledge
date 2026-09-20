<?php
namespace App;

use Illuminate\Database\Eloquent\Model;

class Tours extends Model
{
    protected $table = 'tours';
    public $timestamps = false;
    protected $primaryKey = 'tour_id';

    protected $fillable = [
        'name',
        'description',
        'tour_status_id',
        'tour_type_id',
        'isSeachManuallyEnabled',
        'homepageUrl',
        'themeColor',
        'isPromoCodePopupEnabled',
        'deliveryFee',
        'hasFullDiscount',
        'payment_provider_id',
        'currency_id',
        'face_rec_version',
        'face_rec_first_flow',
        'earlyEmailIntakePopupShow',
    ];
}
