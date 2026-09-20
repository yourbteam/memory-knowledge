<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

class CreateTourDiscountPrerequisites extends Migration
{
    public function up()
    {
        Schema::create('tour_discount_prerequisites', function (Blueprint $table) {
            $table->engine = 'InnoDB';

            $table->integer('checkout_tour_id');
            $table->integer('prerequisite_tour_id');

            $table->primary(
                ['checkout_tour_id', 'prerequisite_tour_id'],
                'tour_discount_prerequisites_primary'
            );

            $table->foreign('checkout_tour_id', 'tdp_checkout_tour_foreign')
                ->references('tour_id')->on('tours');
            $table->foreign('prerequisite_tour_id', 'tdp_prerequisite_tour_foreign')
                ->references('tour_id')->on('tours');
        });
    }

    public function down()
    {
        Schema::dropIfExists('tour_discount_prerequisites');
    }
}
