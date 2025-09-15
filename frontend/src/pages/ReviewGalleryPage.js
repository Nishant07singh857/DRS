import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getReviewById } from '../api/apiService';

// यह एक सिमुलेटेड हॉक-आई कंपोनेंट है
const HawkEyeVisualizer = ({ decision }) => {
    // पिच की स्थिति के आधार पर बॉल का रंग बदलें
    const pitchDotColor = decision.pitch_in_line ? 'bg-green-400' : 'bg-yellow-400';
    // इम्पैक्ट की स्थिति के आधार पर बॉल का रंग बदलें
    const impactDotColor = decision.impact_in_line ? 'bg-green-400' : 'bg-red-400';

    return (
        <div className="bg-green-800/50 p-4 rounded-lg border-2 border-dashed border-white/30 relative aspect-[2/1]">
            {/* Pitch */}
            <div className="absolute left-0 top-1/2 w-full h-[1px] bg-white/30"></div>
            {/* Stumps */}
            <div className="absolute right-[10%] top-[40%] w-[2px] h-[20%] bg-yellow-300"></div>
            <div className="absolute right-[12%] top-[40%] w-[2px] h-[20%] bg-yellow-300"></div>
            <div className="absolute right-[14%] top-[40%] w-[2px] h-[20%] bg-yellow-300"></div>
            
            {/* Ball Trajectory - Simulated */}
            <div className={`absolute left-[20%] top-[45%] w-4 h-4 rounded-full ${pitchDotColor} shadow-lg`} title="Pitching Point"></div>
            <div className="absolute left-[20%] top-[48%] h-[1px] w-[30%] bg-white/50 transform -rotate-2"></div>
            <div className={`absolute left-[50%] top-[40%] w-5 h-5 rounded-full ${impactDotColor} shadow-lg ring-2 ring-white`} title="Impact Point"></div>
            {decision.hitting_wickets && (
                <>
                    <div className="absolute left-[50%] top-[42.5%] h-[1px] w-[32%] bg-red-500/80 transform -rotate-3"></div>
                    <div className="absolute right-[11%] top-[35%] w-4 h-4 rounded-full bg-red-500 shadow-lg" title="Hitting Wickets"></div>
                </>
            )}
        </div>
    );
};


function ReviewDetailPage() {
    const { reviewId } = useParams();
    const [review, setReview] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        getReviewById(reviewId)
            .then(response => {
                setReview(response.data);
            })
            .catch(err => {
                console.error("Failed to fetch review details", err);
                setError("Could not load review details. Please try again.");
            })
            .finally(() => setLoading(false));
    }, [reviewId]);

    if (loading) return <div className="text-center mt-10">Loading review details...</div>;
    if (error) return <div className="text-center mt-10 text-red-500">{error}</div>;
    if (!review) return <div>Review not found.</div>;

    const { decision } = review;
    const decisionColor = decision.final_decision === 'OUT' ? 'text-red-500' : (decision.final_decision === "UMPIRE'S CALL" ? 'text-amber-500' : 'text-green-500');

    return (
        <div className="container mx-auto">
            <h1 className="text-4xl font-bold mb-2">Review Details</h1>
            <p className="text-gray-400 mb-8">Analysis of review created on {new Date(review.created_at).toLocaleString()}</p>
            
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Column: Video and Decision */}
                <div className="lg:col-span-2 space-y-8">
                    <div>
                        <h2 className="text-2xl font-semibold mb-4">Review Video</h2>
                        {/* असली वीडियो प्लेयर यहाँ आएगा */}
                        <div className="bg-black aspect-video w-full rounded-lg flex items-center justify-center text-gray-500">
                             Video Player for <br/> {review.video_url}
                        </div>
                    </div>
                    <div>
                        <h2 className="text-2xl font-semibold mb-4">Hawk-Eye Visualization</h2>
                        <HawkEyeVisualizer decision={decision} />
                    </div>
                </div>

                {/* Right Column: Decision Breakdown */}
                <div className="bg-gray-800 p-6 rounded-lg shadow-lg h-fit">
                    <h2 className="text-2xl font-semibold border-b border-gray-700 pb-3 mb-4">Umpire's Decision</h2>
                    <div className="text-center my-6">
                        <p className={`text-6xl font-bold uppercase ${decisionColor}`}>{decision.final_decision}</p>
                        <p className="text-gray-400 mt-2">Confidence: {decision.confidence}%</p>
                    </div>

                    <div className="space-y-3 text-lg">
                        <div className={`flex justify-between p-3 rounded-md ${decision.pitch_in_line ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                            <span>Pitching</span>
                            <span className="font-bold">{decision.pitch_in_line ? 'IN-LINE' : 'OUTSIDE LEG'}</span>
                        </div>
                        <div className={`flex justify-between p-3 rounded-md ${decision.impact_in_line ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                            <span>Impact</span>
                            <span className="font-bold">{decision.impact_in_line ? 'IN-LINE' : 'OUTSIDE'}</span>
                        </div>
                        <div className={`flex justify-between p-3 rounded-md ${decision.hitting_wickets ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                            <span>Wickets</span>
                            <span className="font-bold">{decision.hitting_wickets ? 'HITTING' : 'MISSING'}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default ReviewDetailPage;
